from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    Account, Product, Review, ProductImage, ProductColor,
    Order, OrderItem, Delivery,
    Payment, Category, Attribute,
)


# ─── Inline: صور المنتج ───────────────────────────────────────────
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    verbose_name = "صورة إضافية"
    verbose_name_plural = "الصور الإضافية"

# ─── Inline: تقييم المنتج ───────────────────────────────────────────
class ReviewInline(admin.TabularInline):
    model = Review
    extra = 1
    verbose_name = "التقييمات"
    verbose_name_plural = "التقييمات"


# ─── Inline: ألوان المنتج ─────────────────────────────────────────
class ProductColorInline(admin.TabularInline):
    model = ProductColor
    extra = 1
    verbose_name = "لون"
    verbose_name_plural = "الألوان"


# ─── Inline: عناصر الطلب ─────────────────────────────────────────
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "color", "quantity")
    can_delete = False
    verbose_name = "عنصر"
    verbose_name_plural = "عناصر الطلب"


# ─── Inline: طلبات المستخدم ──────────────────────────────────────
class OrderInline(admin.TabularInline):
    model = Order
    fields = ("id", "total_price", "status", "order_date")
    readonly_fields = ("id", "total_price", "status", "order_date")
    extra = 0
    can_delete = False
    show_change_link = True  # رابط لفتح الطلب كاملاً
    verbose_name = "طلب"
    verbose_name_plural = "الطلبات"


# ─── Admin: المنتج ────────────────────────────────────────────────
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "price", "stock", "category","created_at")
    list_filter = ("category",)
    search_fields = ("name",)
    inlines = [ProductImageInline, ProductColorInline, ReviewInline]


# ─── Admin: الطلب ────────────────────────────────────────────────
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "account", "total_price", "status", "order_date")
    list_filter = ("status",)
    search_fields = ("account__username",)
    readonly_fields = ("total_price", "order_date")
    inlines = [OrderItemInline]


# ─── Admin: الحساب ───────────────────────────────────────────────
class CustomAccountAdmin(UserAdmin):
    model = Account
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("المعلومات الشخصية"), {"fields": ("first_name", "last_name", "image")}),
        (_("الصلاحيات"), {"fields": (
            "is_active", "is_staff", "is_superuser",
            "isuser", "checked", "groups", "user_permissions",
        )}),
        (_("بيانات التواصل"), {"fields": ("phone_numbers", "address_line")}),
        (_("التواريخ المهمة"), {"fields": ("last_login", "date_joined")}),
        (_("رمز OTP"), {"fields": ("otp_code", "otp_created")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username", "password1", "password2",
                "first_name", "last_name",
                "phone_numbers", "address_line",
            ),
        }),
    )
    list_display = ("id", "username", "first_name", "last_name", "checked", "is_staff")
    list_filter = ("is_staff", "checked", "isuser")
    search_fields = ("username", "first_name", "last_name")
    ordering = ("-date_joined",)
    inlines = [OrderInline]


@admin.register(Account)
class AccountAdmin(CustomAccountAdmin):
    pass


# ─── تسجيل النماذج البسيطة ───────────────────────────────────────
admin.site.register(Review)
admin.site.register(Attribute)
admin.site.register(Category)
admin.site.register(Delivery)
admin.site.register(Payment)
admin.site.register(ProductColor)
admin.site.register(ProductImage)
admin.site.register(OrderItem)