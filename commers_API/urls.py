from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .API import (
    RegisterView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    Logout,
    AccountDetailView,
    Send_otp_Code,
    VerifyOTPView,
    OrderView,
    OrderItemView,
    PaymentView,
    DeliveryView,
    ProductView,
    AttributeView,
    CategoryView,
    ProductImageView,
    ReviewView,
)

# ─── Router للـ ViewSets ──────────────────────────────────────────
router = DefaultRouter()
router.register(r'orders',         OrderView,        basename='orders')
router.register(r'order-items',    OrderItemView,    basename='order-items')
router.register(r'payments',       PaymentView,      basename='payments')
router.register(r'deliveries',     DeliveryView,     basename='deliveries')
router.register(r'products',       ProductView,      basename='products')
router.register(r'attributes',     AttributeView,    basename='attributes')
router.register(r'categories',     CategoryView,     basename='categories')
router.register(r'product-images', ProductImageView, basename='product-images')
router.register(r'review',         ReviewView,           basename='review')

# ─── URL Patterns ─────────────────────────────────────────────────
urlpatterns = [
    # ── المصادقة ──
    path('register/',      RegisterView.as_view(),              name='register'),
    path('token/',         CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(),    name='token_refresh'),
    path('logout/',        Logout.as_view(),                    name='logout'),

    # ── الحساب الشخصي (APIView) ──
    path('account/me/', AccountDetailView.as_view(), name='account_me'),

    # ── OTP ──
    path('Send_otp_Code/',  Send_otp_Code.as_view({'post': 'create'}),  name='send_otp'),
    path('VerifyOTPView/',  VerifyOTPView.as_view({'post': 'create'}),   name='verify_otp'),

    # ── Router URLs ──
    path('', include(router.urls)),
]

# ─── ملفات الوسائط في وضع التطوير فقط ───────────────────────────
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
