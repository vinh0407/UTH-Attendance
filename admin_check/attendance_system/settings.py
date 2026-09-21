"""
Django settings for attendance_system project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('UTH_SECRET_KEY', 'development-only-secret-change-before-deployment-9f1c2e7a')

DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

ALLOWED_HOSTS = ['*']

KIOSK_API_KEY = os.environ.get('UTH_KIOSK_API_KEY', 'development-kiosk-key-change-before-deployment')

# Conservative defaults; calibrate against representative local camera images.
FACE_SIMILARITY_THRESHOLD = float(os.environ.get('UTH_FACE_THRESHOLD', '0.55'))
FACE_MATCH_MARGIN = float(os.environ.get('UTH_FACE_MATCH_MARGIN', '0.04'))
FACE_MIN_DETECTION_SCORE = 0.6
FACE_MIN_SIZE = 60
FACE_MIN_SHARPNESS = 35.0
FACE_CONFIRMATION_FRAMES = 3
FACE_CONFIRMATION_WINDOW_SECONDS = 10
FACE_CONFIRMATION_MIN_INTERVAL_SECONDS = 0.4

# Increase max upload size for face images (50MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SECURE_REFERRER_POLICY = 'same-origin'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Local apps
    'portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'attendance_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'attendance_system.wsgi.application'

# Database - SQLite (dễ chạy, không cần cài MySQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '0') == '1'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'standard': {'format': '{levelname} {asctime} {name} {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'}},
    'loggers': {
        'portal': {'handlers': ['console'], 'level': os.environ.get('UTH_LOG_LEVEL', 'INFO'), 'propagate': False},
        'django.request': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================================
# OpenCV Plugin Configuration
# =====================================================
# Cấu hình URL cho plugin OpenCV - thay đổi theo nhu cầu
OPENCV_PLUGIN_URL = '/scan/camera/'  # URL tới plugin OpenCV của anh
ADMIN_DASHBOARD_URL = '/admin-dashboard/'
REGISTER_FACE_URL = '/register/'

# Optional CSV backup/integration drop folder. Realtime attendance still uses
# the Kiosk -> Django API path; this folder is only for explicit imports.
ATTENDANCE_IMPORT_DIR = BASE_DIR.parent / 'APP' / 'Máy điểm danh' / 'inbox'
STUDENT_DATA_DIR = BASE_DIR.parent / 'APP' / 'Dữ liệu' / 'Sinh viên trường'
ATTENDANCE_HISTORY_DIR = BASE_DIR.parent / 'APP' / 'Dữ liệu' / 'Lịch sử điểm danh'
