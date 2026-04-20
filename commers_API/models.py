from email.policy import default
from enum import unique
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.db.models import Avg

# ─── الألوان المتاحة ─────────────────────────────────────────────
COLOR_CHOICES = [
    ('red', 'أحمر'),
    ('blue', 'أزرق'),
    ('green', 'أخضر'),
    ('yellow', 'أصفر'),
    ('black', 'أسود'),
    ('white', 'أبيض'),
    ('purple', 'بنفسجي'),
    ('orange', 'برتقالي'),
    ('pink', 'وردي'),
    ('brown', 'بني'),
]

# ─── حالات الطلب ─────────────────────────────────────────────────
ORDER_STATUS = (
    ('Pending', 'Pending'),
    ('Shipped', 'Shipped'),
    ('Delivered', 'Delivered'),
    ('Cancelled', 'Cancelled'),
)

# ─── حالات الدفع ─────────────────────────────────────────────────
PAYMENT_STATUS = (
    ('Completed', 'Completed'),
    ('Pending', 'Pending'),
    ('Failed', 'Failed'),
)

PAYMENT_METHODS = (
    ('On Delivery', 'On Delivery'),
    ('Barid mob', 'Barid mob'),
    ('Bank Transfer', 'Bank Transfer'),
)
DELIVERY_TYPE = (
    ('normal', 'normal'),
    ('fast', 'fast'),
)


# ─── حساب المستخدم ───────────────────────────────────────────────
class Account(AbstractUser):
    otp_code = models.CharField(max_length=128, null=True, blank=True)
    otp_created = models.DateTimeField(null=True, blank=True)
    address_line = models.JSONField(default=dict, blank=True)
    phone_numbers = models.JSONField(default=list, blank=True)
    checked = models.BooleanField(default=False)
    image = models.ImageField(upload_to='Profile_image/', blank=True)
    isuser = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        # تحويل اسم المستخدم لأحرف صغيرة عند الإنشاء فقط
        if not self.pk and self.username:
            self.username = self.username.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Account {self.id} - {self.username}"


# ─── الخصائص ─────────────────────────────────────────────────────
class Attribute(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


# ─── التصنيفات ───────────────────────────────────────────────────
class Category(models.Model):
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default='black')

    def __str__(self):
        return self.name


# ─── المنتج ──────────────────────────────────────────────────────
class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    category = models.ForeignKey(
        'Category', related_name='products', on_delete=models.CASCADE
    )

    stock = models.PositiveIntegerField(default=0)
    attributes = models.ManyToManyField('Attribute', related_name='products', blank=True)

    rating = models.FloatField(default=0)
    reviews_count = models.PositiveIntegerField(default=0)

    primary_image = models.ImageField(
        upload_to='product_images/',
        blank=True,
        default='product_images/defult.png'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sales = models.FloatField(default=0)
    discount = models.FloatField(default=0)
    
    def __str__(self):
        return self.name

# ─── تقييم المنتج ────────────────────────────────────────────────
class Review(models.Model):
    product = models.ForeignKey(
        Product, related_name='reviews', on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    stars = models.DecimalField(max_digits=2,decimal_places=1,default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def update_product_rating(self):
        product = self.product
        data = product.reviews.aggregate(avg=Avg("stars"))

        product.rating = data["avg"] or 0
        product.reviews_count = product.reviews.count()
        product.save(update_fields=["rating", "reviews_count"])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_product_rating()

    def delete(self, *args, **kwargs):
        product = self.product
        super().delete(*args, **kwargs)

        data = product.reviews.aggregate(avg=Avg("stars"))
        product.rating = data["avg"] or 0
        product.reviews_count = product.reviews.count()
        product.save(update_fields=["rating", "reviews_count"])

# ─── ألوان المنتج ────────────────────────────────────────────────
class ProductColor(models.Model):
    product = models.ForeignKey(
        Product, related_name='colors', on_delete=models.CASCADE
    )
    # اللون من القائمة المحددة (اختياري)
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, blank=True, default='')
    # أو اسم لون مخصص
    color_name = models.CharField(max_length=50, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        label = self.color or self.color_name
        return f"{self.product.name} - {label} ({self.quantity})"


# ─── صور المنتج الإضافية ─────────────────────────────────────────
class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, related_name='secondary_images', on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to='product_images/')

    def __str__(self):
        return f"{self.product.name} - Image"


# ─── الطلب ───────────────────────────────────────────────────────
class Order(models.Model):
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='orders', on_delete=models.CASCADE
    )
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=50, choices=ORDER_STATUS, default='Pending'
    )
    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    def calculate_total_price(self):
        return sum(
            item.product.price * item.quantity
            for item in self.items.all()
        )

    def save(self, *args, **kwargs):
        # حفظ أولي للحصول على pk
        if not self.pk:
            super().save(*args, **kwargs)
        self.total_price = self.calculate_total_price()
        super().save(update_fields=['total_price'])

    def __str__(self):
        return f"Order {self.id} by {self.account.username}"


# ─── عناصر الطلب ─────────────────────────────────────────────────
class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, related_name='items', on_delete=models.CASCADE
    )
    product = models.ForeignKey(
        Product, related_name='order_items', on_delete=models.PROTECT
    )
    color = models.CharField(max_length=50, default='none', blank=True)
    size = models.CharField(max_length=20, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # تحديث إجمالي الطلب تلقائياً
        self.order.total_price = self.order.calculate_total_price()
        self.order.save(update_fields=["total_price"])

    def delete(self, *args, **kwargs):
        order = self.order
        super().delete(*args, **kwargs)
        # إعادة حساب الإجمالي بعد الحذف
        order.save()

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in Order {self.order.id}"


# ─── التوصيل ─────────────────────────────────────────────────────
class Delivery(models.Model):
    delivery_order = models.ForeignKey(
        Order, related_name='deliveries', on_delete=models.CASCADE
    )
    first_name = models.CharField(max_length=50, blank=False)
    last_name = models.CharField(max_length=50, blank=False)
    delivery_address = models.JSONField(default=dict, blank=False)
    delivery_phone = models.JSONField(default=list, blank=False)
    payment = models.CharField(
        max_length=50, choices=PAYMENT_METHODS, default='On Delivery'
    )
    delivery_type = models.CharField(choices=DELIVERY_TYPE, default='normal')

    def __str__(self):
        return f"Delivery for Order {self.delivery_order.id} → {self.first_name} {self.last_name}"


# ─── الدفع ───────────────────────────────────────────────────────
class Payment(models.Model):
    order = models.OneToOneField(
        Order, related_name='payment', on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(
        max_length=50, choices=PAYMENT_METHODS, default='On Delivery'
    )
    payment_status = models.CharField(
        max_length=50, choices=PAYMENT_STATUS, default='Pending'
    )

    def __str__(self):
        return f"Payment for Order {self.order.id} - {self.amount}"