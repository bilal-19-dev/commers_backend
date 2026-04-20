from dataclasses import field
from django.db import models
from rest_framework import serializers
from .models import (
    Account, Order, OrderItem, Delivery,
    Payment, Product, Review, Attribute, Category,
    ProductImage, ProductColor,
)
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import re


# ─── Serializer الصور الإضافية ───────────────────────────────────
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = '__all__'


# ─── Serializer ألوان المنتج ──────────────────────────────────────
class ProductColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductColor
        exclude = ["product", "id"]


# ─── Serializer تقييم المنتج  ────────────────────────────────────

class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = '__all__'
        extra_kwargs = {'user': {'read_only': True}}

    def create(self, validated_data):
        user = self.context["request"].user
        product = validated_data["product"]

        review, created = Review.objects.update_or_create(
            user=user,
            product=product,
            defaults={"stars": validated_data["stars"]}
        )
        return review
# ─── Serializer المنتج الكامل ────────────────────────────────────
class ProductSerializer(serializers.ModelSerializer):
    secondary_images = ProductImageSerializer(many=True, read_only=True)
    colors = ProductColorSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = '__all__'


# ─── Serializer المنتج داخل الطلبات ──────────────────────────────
class ProductOrderSerializer(serializers.ModelSerializer):
    """يُستخدم لعرض بيانات المنتج ضمن الطلبات مع رابط الصورة الكامل"""

    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        exclude = ["stock", "category", "attributes"]

    def get_primary_image(self, obj):
        request = self.context.get("request")
        if obj.primary_image and request:
            return request.build_absolute_uri(obj.primary_image.url)
        return None


# ─── Serializer عناصر الطلب (للقراءة) ───────────────────────────
class OrderItemReadSerializer(serializers.ModelSerializer):
    product = ProductOrderSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = '__all__'
        extra_kwargs = {'order': {'read_only': True}}


# ─── Serializer عناصر الطلب (للكتابة) ───────────────────────────
class OrderItemWriteSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'color']


# ─── Serializer التوصيل ──────────────────────────────────────────
class DeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = Delivery
        fields = '__all__'
        extra_kwargs = {'delivery_order': {'read_only': True}}


# ─── Serializer الطلب ────────────────────────────────────────────
class OrderSerializer(serializers.ModelSerializer):
    # للقراءة
    items = serializers.SerializerMethodField()
    items_count = serializers.SerializerMethodField()

    # للكتابة
    items_register = OrderItemWriteSerializer(many=True, write_only=True)
    deliveries = DeliverySerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = '__all__'
        extra_kwargs = {
            'total_price': {'read_only': True},
            'account': {'read_only': True},
        }

    def validate(self, attrs):
        """التحقق من بيانات التوصيل والعناصر"""
        request = self.context.get("request")
        items_data = attrs.get('items_register', [])
        deliveries_data = attrs.get('deliveries', [])

        # التحقق من وجود عناصر
        if not items_data:
            raise serializers.ValidationError({"error": "The items are required."})

        # المستخدم المجهول يحتاج بيانات التوصيل
        if request and request.user.username == "@Anonimo":
            if not deliveries_data:
                raise serializers.ValidationError({
                    "error": "Delivery info is required for anonymous users."
                })

        # التحقق من بيانات التوصيل
        phone_regex = re.compile(r'^(05|06|07|02)\d{8}$')

        for delivery in deliveries_data:
            first_name = delivery.get("first_name", "").strip()
            last_name = delivery.get("last_name", "").strip()
            address = delivery.get("delivery_address", {})
            phones = delivery.get("delivery_phone", [])

            wilaya = address.get("wilaya", "").strip()
            baldya = address.get("baldya", "").strip()

            if not first_name or len(first_name) < 3:
                raise serializers.ValidationError({
                    "error": "First name must be at least 3 characters."
                })
            if not last_name or len(last_name) < 3:
                raise serializers.ValidationError({
                    "error": "Last name must be at least 3 characters."
                })
            if not wilaya or not baldya:
                raise serializers.ValidationError({
                    "error": "Please enter your full address (wilaya and baldya)."
                })
            if not phones or not isinstance(phones, list) or len(phones) == 0:
                raise serializers.ValidationError({
                    "error": "At least one phone number is required."
                })
            if not phones[0] or not phones[0].strip():
                raise serializers.ValidationError({
                    "error": "Please enter your phone number."
                })
            for phone in phones:
                if phone and not phone_regex.match(phone):
                    raise serializers.ValidationError({
                        "error": "Phone numbers must start with 05, 06, 07 or 02 and be 10 digits."
                    })

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        items_data = validated_data.pop('items_register', [])
        deliveries_data = validated_data.pop('deliveries', [])

        # إنشاء الطلب
        order = Order.objects.create(account=request.user, **validated_data)

        # إنشاء عناصر الطلب والتحقق من المخزون
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data.get('quantity', 1)
            color = item_data.get('color', '')

            # التحقق من توفر اللون والكمية
            color_obj = product.colors.filter(
                models.Q(color=color) | models.Q(color_name=color)
            ).first()

            if color_obj:
                if color_obj.quantity < quantity:
                    raise serializers.ValidationError({
                        "error": f"Not enough stock for {product.name} in color {color}."
                    })
                # تقليل المخزون
                color_obj.quantity -= quantity
                color_obj.save()

            OrderItem.objects.create(order=order, **item_data)

        # إنشاء بيانات التوصيل
        for delivery_data in deliveries_data:
            Delivery.objects.create(delivery_order=order, **delivery_data)

        return order

    def get_items_count(self, obj):
        return obj.items.count()

    def get_items(self, obj):
        return OrderItemReadSerializer(
            obj.items.all(), many=True, context=self.context
        ).data


# ─── Serializer الحساب ───────────────────────────────────────────
class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        exclude = [
            "groups", "user_permissions",
            "is_active", "is_staff", "is_superuser", "email",
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False},
            'username': {'required': False},
        }

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# ─── Serializer التسجيل ──────────────────────────────────────────
class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            'username', 'password', 'phone_numbers',
            'first_name', 'last_name', 'image', 'address_line',
        ]
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        return Account.objects.create_user(**validated_data)


# ─── Serializer JWT Token ─────────────────────────────────────────
class ObtainTokenPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['checked'] = user.checked
        token['id'] = user.id
        return token


# ─── Serializer الخصائص ──────────────────────────────────────────
class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attribute
        fields = '__all__'


# ─── Serializer التصنيفات ────────────────────────────────────────
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


# ─── Serializer الدفع ────────────────────────────────────────────
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'