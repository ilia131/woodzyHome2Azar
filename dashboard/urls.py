from django.urls import path

from .api import (
    DashboardFavorites, DashboardNotifications, DashboardOverview, DashboardReviews, DashboardSearches, DashboardViews,
)

urlpatterns = [
    path('overview/', DashboardOverview.as_view(), name='dashboard-overview'),
    path('favorites/', DashboardFavorites.as_view(), name='dashboard-favorites'),
    path('reviews/', DashboardReviews.as_view(), name='dashboard-reviews'),
    path('searches/', DashboardSearches.as_view(), name='dashboard-searches'),
    path('views/', DashboardViews.as_view(), name='dashboard-views'),
    path('notifications/', DashboardNotifications.as_view(), name='dashboard-notifications'),
]
