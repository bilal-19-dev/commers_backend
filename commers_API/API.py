import random
import re
from django.db.models import F

import dns.resolver
from django.contrib.auth.hashers import check_password
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ViewSet

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import TokenError

from .models import (
    Account, Order, OrderItem, Delivery,
    Payment, Product, Attribute, Category,
    ProductColor, ProductImage, Review
)
from .Serializer import (
    RegisterSerializer, ObtainTokenPairSerializer,
    OrderSerializer, PaymentSerializer, DeliverySerializer,
    OrderItemWriteSerializer, ProductSerializer,
    AttributeSerializer, CategorySerializer,
    ProductImageSerializer, AccountSerializer,
    ReviewSerializer
)
from rest_framework.decorators import api_view

# ─── ثوابت ───────────────────────────────────────────────────────
PHONE_REGEX = re.compile(r'^(05|06|07|02)\d{8}$')


# ─── دوال مساعدة ─────────────────────────────────────────────────
def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(email_address, code):
    send_mail(
        subject="كود التحقق",
        message=f"كود التحقق الخاص بك هو: {code}",
        from_email=None,
        recipient_list=[email_address],
        fail_silently=False,
    )


def validate_phone_numbers(phone_numbers):
    """التحقق من صحة أرقام الهاتف، تُرجع رسالة خطأ أو None"""
    if not phone_numbers or len(phone_numbers) == 0:
        return "phone1", "رقم الهاتف مطلوب"
    if not phone_numbers[0] or not phone_numbers[0].strip():
        return "phone1", "رقم الهاتف مطلوب"
    if not PHONE_REGEX.match(phone_numbers[0]):
        return "phone1", "رقم الهاتف الأول غير صحيح، يجب أن يبدأ ب 05/06/07/02 ويكون 10 أرقام."
    if len(phone_numbers) > 1 and phone_numbers[1]:
        if not PHONE_REGEX.match(phone_numbers[1]):
            return "phone2", "رقم الهاتف الثاني غير صحيح، يجب أن يبدأ ب 05/06/07/02 ويكون 10 أرقام."
        if phone_numbers[0] == phone_numbers[1]:
            return "phone2", "رقم الهاتف الثاني يجب أن يكون مختلف عن الأول"
    return None, None


def validate_delivery(delivery_dict):
    """التحقق من بيانات التوصيل، تُرجع رسالة خطأ أو None"""
    first_name = (delivery_dict.get("first_name") or "").strip()
    last_name = (delivery_dict.get("last_name") or "").strip()
    address = delivery_dict.get("delivery_address") or {}
    phones = delivery_dict.get("delivery_phone") or []

    wilaya = (address.get("wilaya") or "").strip()
    baldya = (address.get("baldya") or "").strip()

    if not first_name or len(first_name) < 3:
        return "الاسم الأول يجب أن يكون 3 أحرف على الأقل"
    if not last_name or len(last_name) < 3:
        return "اللقب يجب أن يكون 3 أحرف على الأقل"
    if not wilaya or not baldya:
        return "يرجى إدخال العنوان الكامل (الولاية والبلدية)"

    field, msg = validate_phone_numbers(phones)
    if msg:
        return msg

    return None


def validate_email_domain(username):
    """التحقق من نطاق البريد الإلكتروني"""
    if "@" not in username or len(username.split("@")) != 2:
        return "Invalid email format"
    domain = username.split("@")[1]
    try:
        dns.resolver.resolve(domain, 'MX')
    except (
        dns.resolver.NXDOMAIN,
        dns.resolver.NoAnswer,
        dns.resolver.NoNameservers,
        dns.resolver.Timeout,
    ):
        return "Invalid email domain"
    return None


# ─── تسجيل حساب جديد ─────────────────────────────────────────────
class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        address_line = data.get("address_line", {})
        username = data.get("username", "")
        phone_numbers = data.get("phone_numbers", [])

        # التحقق من الاسم
        if not first_name or len(first_name) < 3:
            return Response(
                {"firstName": "الاسم مطلوب ويجب أن يكون 3 أحرف على الأقل"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not last_name or len(last_name) < 3:
            return Response(
                {"lastName": "اللقب مطلوب ويجب أن يكون 3 أحرف على الأقل"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # التحقق من العنوان
        wilaya = address_line.get("wilaya", "").strip()
        commune = (address_line.get("baldya") or address_line.get("commune") or "").strip()
        if not wilaya:
            return Response({"wilaya": "يرجى إدخال الولاية"}, status=status.HTTP_400_BAD_REQUEST)
        if not commune:
            return Response({"commune": "يرجى إدخال البلدية"}, status=status.HTTP_400_BAD_REQUEST)

        # التحقق من البريد الإلكتروني
        if not username:
            return Response({"email": "البريد الإلكتروني مطلوب"}, status=status.HTTP_400_BAD_REQUEST)
        if Account.objects.filter(username__iexact=username).exists():
            return Response({"email": "البريد الإلكتروني مستخدم بالفعل"}, status=status.HTTP_400_BAD_REQUEST)

        domain_error = validate_email_domain(username)
        if domain_error:
            return Response({"email": domain_error}, status=status.HTTP_400_BAD_REQUEST)

        # التحقق من الهاتف
        field, phone_error = validate_phone_numbers(phone_numbers)
        if phone_error:
            return Response({field: phone_error}, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        return Response(
            {"message": "تم إنشاء الحساب بنجاح", "user_id": user.id, "username": user.username},
            status=status.HTTP_201_CREATED,
        )


# ─── إرسال كود OTP ───────────────────────────────────────────────
class Send_otp_Code(ViewSet):
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request):
        email = request.data.get("username", "").strip()
        if not email:
            return Response({"email": "البريد الإلكتروني مطلوب"}, status=400)

        user = Account.objects.filter(username__iexact=email).first()
        if not user:
            return Response({"email": "المستخدم غير موجود"}, status=400)

        code = generate_otp()
        user.otp_code = code
        user.otp_created = timezone.now()
        user.save(update_fields=["otp_code", "otp_created"])

        send_otp_email(user.username, code)  # username هو البريد الإلكتروني

        return Response({"message": f"تم إرسال كود التحقق إلى {user.username}"})


# ─── التحقق من كود OTP ───────────────────────────────────────────
class VerifyOTPView(ViewSet):
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request):
        email = request.data.get("username", "").strip()
        code = request.data.get("code", "").strip()

        user = Account.objects.filter(username__iexact=email).first()
        if not user:
            return Response({"email": "المستخدم غير موجود"}, status=400)
        if user.otp_code != code:
            return Response({"code": "الكود غير صحيح"}, status=400)
        if not user.otp_created or timezone.now() > user.otp_created + timezone.timedelta(minutes=5):
            return Response({"code": "انتهت صلاحية الكود"}, status=400)

        # مسح الكود بعد الاستخدام
        user.otp_code = None
        user.otp_created = None
        user.save(update_fields=["otp_code", "otp_created"])

        # إنشاء التوكن
        refresh = RefreshToken.for_user(user)
        refresh["username"] = user.username
        refresh["checked"] = user.checked
        access = refresh.access_token

        response = Response({"refresh": str(refresh), "access": str(access)})
        response.set_cookie(key='access', value=str(access), httponly=True, secure=True, samesite='None',path='/')
        response.set_cookie(key='refresh', value=str(refresh), httponly=True, secure=True, samesite='None',path='/')
        return response


# ─── تسجيل الدخول ────────────────────────────────────────────────
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = ObtainTokenPairSerializer

    def post(self, request, *args, **kwargs):
        username = request.data.get("username", "").strip()
        password = request.data.get("password", "")

        user = Account.objects.filter(username__iexact=username).first()
        if not user:
            return Response({"email": "المستخدم غير موجود"}, status=400)
        if not check_password(password, user.password):
            return Response({"password": "كلمة المرور خاطئة"}, status=400)

        response = super().post(request, *args, **kwargs)
        data = response.data

        response.set_cookie(key='access', value=data.get('access'), httponly=True, secure=True, samesite='None',path='/')
        response.set_cookie(key='refresh', value=data.get('refresh'), httponly=True, secure=True, samesite='None',path='/')
        return response


# ─── تحديث التوكن ────────────────────────────────────────────────
class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get('refresh')

        if not refresh:
            res = Response({"detail": "No refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
            res.delete_cookie('access')
            res.delete_cookie('refresh')
            return res

        request.data['refresh'] = refresh

        try:
            response = super().post(request, *args, **kwargs)
        except TokenError:
            res = Response({"detail": "Refresh token expired"}, status=status.HTTP_401_UNAUTHORIZED)
            res.delete_cookie('access')
            res.delete_cookie('refresh')
            return res

        response.set_cookie(
            key='access', value=response.data.get('access'),
            httponly=True, secure=True, samesite='None',
        )
        return response


# ─── إدارة الحساب الشخصي ─────────────────────────────────────────
class AccountDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """جلب بيانات المستخدم وطلباته"""
        user = request.user
        if user.username == "@Anonimo" :
            return Response({"error_user": "غير مسموح"}, status=400)
        user_data = AccountSerializer(user, context={"request": request}).data
        orders = user.orders.prefetch_related("items__product", "deliveries").all()
        orders_data = OrderSerializer(orders, many=True, context={"request": request}).data
        return Response({"user": user_data, "orders": orders_data})

    def patch(self, request):
        """تعديل بيانات الحساب"""
        user = request.user
        serializer = AccountSerializer(user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        first_name = (data.get("first_name") or "").strip()
        last_name = (data.get("last_name") or "").strip()
        address_line = data.get("address_line")
        username = data.get("username", "")
        phone_numbers = data.get("phone_numbers")
        password = data.get("password")

        if first_name and len(first_name) < 3:
            return Response({"firstName": "الاسم يجب أن يكون 3 أحرف على الأقل"}, status=400)
        if last_name and len(last_name) < 3:
            return Response({"lastName": "اللقب يجب أن يكون 3 أحرف على الأقل"}, status=400)

        if address_line:
            wilaya = (address_line.get("wilaya") or "").strip()
            commune = (address_line.get("baldya") or address_line.get("commune") or "").strip()
            if not wilaya:
                return Response({"wilaya": "يرجى إدخال الولاية"}, status=400)
            if not commune:
                return Response({"commune": "يرجى إدخال البلدية"}, status=400)

        if username:
            if Account.objects.filter(username__iexact=username).exclude(pk=user.pk).exists():
                return Response({"email": "البريد الإلكتروني مستخدم بالفعل"}, status=400)
            domain_error = validate_email_domain(username)
            if domain_error:
                return Response({"email": domain_error}, status=400)

        if phone_numbers:
            field, phone_error = validate_phone_numbers(phone_numbers)
            if phone_error:
                return Response({field: phone_error}, status=400)

        if password:
            code = request.data.get("code", "").strip()
            if not code:
                return Response({"code": "من فضلك أدخل رمز التحقق"}, status=400)
            if user.otp_code != code:
                return Response({"code": "الكود غير صحيح"}, status=400)
            if not user.otp_created or timezone.now() > user.otp_created + timezone.timedelta(minutes=5):
                return Response({"code": "انتهت صلاحية الكود"}, status=400)
            if check_password(password, user.password):
                return Response({"password": "استخدم كلمة مرور جديدة"}, status=400)

        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        """حذف صورة الملف الشخصي"""
        user = request.user
        if user.image:
            user.image.delete(save=False)
            user.image = None
            user.save(update_fields=["image"])
        return Response(AccountSerializer(user).data)


# ─── إنشاء الطلب ─────────────────────────────────────────────────
class OrderView(ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        items = request.data.get("items", [])
        deliveries_data = request.data.get("deliveries", [])
        if not items:
            return Response({"error": "The items are required"}, status=status.HTTP_400_BAD_REQUEST)

        # التحقق من بيانات التوصيل للمستخدم المجهول
        if request.user.username == "@Anonimo" and not deliveries_data:
            return Response(
                {"error": "Delivery info is required for anonymous users."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # التحقق من بيانات التوصيل قبل بدء المعاملة
        for delivery_dict in deliveries_data:
            error = validate_delivery(delivery_dict)
            if error:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                order = Order.objects.create(account=request.user)

                # إنشاء عناصر الطلب وتقليل المخزون
                for item_data in items:
                    product_id = item_data.get("product")
                    color = item_data.get("color", "")
                    quantity = item_data.get("quantity", 1)

                    product = Product.objects.filter(pk=product_id).first()

                    if not product:
                        raise serializers.ValidationError({
                            "error": f"Product with id {product_id} not found."
                        })

                    updated = Product.objects.filter(pk=product_id).update(sales=F('sales') + 1)

                    product_color = (
                        ProductColor.objects.select_for_update()
                        .filter(product=product)
                        .filter(
                            models.Q(color=color) | models.Q(color_name=color)
                        )
                        .first()
                    )

                    if not product_color:
                        raise serializers.ValidationError({
                            "error": f"The color '{color}' is not available for '{product.name}'."
                        })

                    if product_color.quantity < quantity:
                        raise serializers.ValidationError({
                            "error": f"Not enough stock for color '{color}' of '{product.name}'."
                        })

                    product_color.quantity -= quantity
                    product_color.save(update_fields=["quantity"])

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        color=color,
                        quantity=quantity,
                    )

                # إنشاء بيانات التوصيل (مرة واحدة فقط خارج حلقة items)
                for delivery_dict in deliveries_data:
                    Delivery.objects.create(delivery_order=order, **delivery_dict)

                return Response(
                    {"message": "تم إنشاء الطلب بنجاح", "order_id": order.id},
                    status=status.HTTP_201_CREATED,
                )

        except serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ─── المنتجات ─────────────────────────────────────────────────────
class ProductView(ModelViewSet):
    queryset = Product.objects.prefetch_related("colors", "secondary_images").all()
    serializer_class = ProductSerializer
    lookup_field = 'id'
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'], url_path='by-ids')
    def by_ids(self, request):
        ids = request.data.get("ids", [])
        products = Product.objects.filter(id__in=ids).prefetch_related("colors", "secondary_images")
        return Response(self.get_serializer(products, many=True).data)


# ─── التصنيفات ───────────────────────────────────────────────────
class CategoryView(ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ─── باقي الـ ViewSets ────────────────────────────────────────────
class PaymentView(ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]


class DeliveryView(ModelViewSet):
    queryset = Delivery.objects.all()
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]


class OrderItemView(ModelViewSet):
    queryset = OrderItem.objects.all()
    serializer_class = OrderItemWriteSerializer
    permission_classes = [IsAuthenticated]


class AttributeView(ModelViewSet):
    queryset = Attribute.objects.all()
    serializer_class = AttributeSerializer


class ProductImageView(ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer


# ─── تسجيل الخروج ────────────────────────────────────────────────
class Logout(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        res = Response({"detail": "تم تسجيل الخروج بنجاح"})
        res.delete_cookie('access')
        res.delete_cookie('refresh')
        return res


class ReviewView(ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)
    def perform_create(self, serializer):
        if user.username == "@Anonimo" :
            return Response({"user": "غير مسموح"}, status=400)
        serializer.save(user=self.request.user)
    @action(detail=False, methods=['delete'])
    def delete_by_product(self, request):
        product = request.query_params.get("product")
        if user.username == "@Anonimo" :
            return Response({"user": "غير مسموح"}, status=400)
        review = Review.objects.filter(
            user=request.user,
            product_id=product
        ).first()

        if not review:
            return Response({"message": "التقييم غير موجود"}, status=400)

        review.delete()
        return Response({"message": "تم الحذف بنجاح"}, status=204)