"""
Django settings for fir_ser project.

Generated by 'django-admin startproject' using Django 3.0.3.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'j!g@^bc(z(a3*i&kp$_@bgb)bug&^#3=amch!3lz&1x&s6ss6t'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'synchrotron', '172.16.133.34', 'ali.cdn.flyapp.dvcloud.xin',
                 'api.src.flyapp.dvcloud.xin']

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'api.apps.ApiConfig',
    'rest_framework',
    'captcha',
    'django_celery_beat',
    'django_celery_results',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.utils.middlewares.CorsMiddleWare'
]

ROOT_URLCONF = 'fir_ser.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
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

WSGI_APPLICATION = 'fir_ser.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    # },
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'flyapp',
        'USER': 'flyuser',
        'PASSWORD': 'KGzKjZpWBp4R4RSa',
        'HOST': '127.0.0.1',
        'PORT': '3306',
        # 设置MySQL的驱动
        # 'OPTIONS': {'init_command': 'SET storage_engine=INNODB'},
        'OPTIONS': {'init_command': 'SET sql_mode="STRICT_TRANS_TABLES"', 'charset': 'utf8mb4'}
    }

}

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

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

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'api.utils.throttle.LoginUserThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'ShortAccessUser1': '180/m',
        'ShortAccessUser2': '2000/h',
        'LoginUser': '200/m',
        'RegisterUser1': '40/m',
        'RegisterUser2': '300/h',
        'GetAuthC1': '60/m',
        'GetAuthC2': '300/h',
        'InstallAccess1': '10/m',
        'InstallAccess2': '20/h',
    }
}
# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = False

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static")
]

# Media配置
MEDIA_URL = "files/"
MEDIA_ROOT = os.path.join(BASE_DIR, "files")
# supersign配置
SUPER_SIGN_ROOT = os.path.join(BASE_DIR, "supersign")

AUTH_USER_MODEL = "api.UserInfo"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 100},
            "PASSWORD": "",
            "DECODE_RESPONSES": True
        },
        "TIMEOUT": 60 * 15
    },
}

# DRF扩展缓存时间
REST_FRAMEWORK_EXTENSIONS = {
    # 缓存时间
    'DEFAULT_CACHE_RESPONSE_TIMEOUT': 3600,
    # 缓存存储
    'DEFAULT_USE_CACHE': 'default',
}

# geetest 配置信息
GEETEST_ID = "d3f3cf73200a70bd3a0c32ea22e5003a"
GEETEST_KEY = "6f4ab6185c230a4b1f8430f28ebe4804"
GEETEST_CYCLE_TIME = 10
GEETEST_BYPASS_STATUS_KEY = "gt_server_bypass_status"
GEETEST_BYPASS_URL = "http://bypass.geetest.com/v1/bypass_status.php"

# 注册方式，如果启用sms或者email 需要配置 THIRD_PART_CONFIG.sender 信息
REGISTER = {
    "enable": True,
    "captcha": False,  # 是否开启注册字母验证码
    "geetest": True,  # 是否开启geetest验证，如要开启请先配置geetest
    "register_type": {
        'sms': True,  # 短信注册
        'email': True,  # 邮件注册
        'code': False,  # 邀请码注册,邀请码必填写，需要和短信，邮件一起使用
    }
}
# 个人资料修改修改也会使用该配置
CHANGER = {
    "enable": True,
    "captcha": False,  # 是否开启注册字母验证码
    "geetest": True,  # 是否开启geetest验证，如要开启请先配置geetest
    "change_type": {
        'sms': True,  # 短信注册
        'email': True,  # 邮件注册
        'code': False,  # 邀请码注册,邀请码必填写，需要和短信，邮件一起使用
    }
}
LOGIN = {
    "captcha": False,  # 是否开启登录字母验证码
    "geetest": True,  # 是否开启geetest验证
    "login_type": {
        'sms': True,  # 短信登录
        'email': True,  # 邮件登录
        'up': True,  # 密码登录
    }
}

THIRD_PART_CONFIG = {
    # APP存储配置
    'storage': [
        {
            'name': 'local',
            'type': 0,
            'auth': {
                'domain_name': 'app.hehelucky.cn',
                # 正式环境需要填写正式的访问域名,如果配置cdn，可以填写cdn的域名，仅支持阿里云 cdn,
                # 开启cdn之后，如果该域名和服务器域名不相同，需要设置阿里云cdn 缓存配置，自定义HTTP响应头 添加 Access-Control-Allow-Origin * 才可以
                'is_https': True,
                'download_auth_type': 1,  # 0:不开启token 1:本地token 2:cdn 开启cdn，并且使用本地存储，使用阿里云cdn进行url鉴权，
                'cnd_auth_key': '',  # 当cdn为阿里云并且 download_auth_type=2 的时候 生效,需要 开启阿里云OSS私有Bucket回源
            },
            'active': True
        },
        {
            'name': 'aliyun',
            'type': 2,
            'auth': {
                'access_key': 'LTAI4FkbTR',
                'secret_key': '2iLIxy9',
                'bucket_name': 'fge',
                'sts_role_arn': 'ap-sage',
                'endpoint': 'oss-cn-beijing-internal.aliyuncs.com',  # 服务器和oss在同一个地区，填写内网的endpoint
                'is_https': True,
                'domain_name': 'aoud.xin',
                'download_auth_type': 1,  # 1:oss 2:cdn
                'cnd_auth_key': '',  # 当cdn为阿里云并且 download_auth_type=2 的时候 生效,需要 开启阿里云OSS私有Bucket回源
            },
            'active': False
        },
        {
            'name': 'qiniuyun',
            'type': 1,
            'auth': {
                'access_key': 'mT4fiJ',
                'secret_key': '0G9fXfhYLynv',
                'bucket_name': 'fge',
                'is_https': False,
                'domain_name': 'foud.xin'
            },
            'active': False
        }
    ],
    'sender': [
        {
            'name': 'email',
            'type': 0,
            'auth': {
                'email_host': 'smtp.126.com',
                'email_port': 465,
                'use_tls': False,
                'use_ssl': True,
                'username': 'flyapps@126.com',
                'password': 'GGHFEUMZBRZIFZGQ',
                'form': 'FlyApp Validation <flyapps@126.com>',
                'subject': '%(code)s验证',
                'template_code': {
                    'login': '欢迎使用FLY 应用分发平台。 您的验证码%(code)s，您正在登录，若非本人操作，请勿泄露。',
                    'change': '欢迎使用FLY 应用分发平台。 您的验证码%(code)s，您正在尝试变更重要信息，请妥善保管账户信息。',
                    'register': '欢迎使用FLY 应用分发平台。 您的验证码%(code)s，您正在注册成为新用户，感谢您的支持！',
                }
            },
            'active': True
        },
        {
            'name': 'aliyun',
            'type': 1,
            'auth': {
                'access_key': 'LTAI5tJH2EnjVzJGMmNCYo9U',
                'secret_key': 'd0LETks5oxkdfbkLGtFihklWGbokab',
                'region_id': 'cn-hangzhou',
                'sing_name': '合合相亲',
                'template_code': {
                    'login': 'SMS_177185094',
                    'change': 'SMS_177185090',
                    'register': 'SMS_177185092',
                }
            },
            'active': False
        },
        {
            'name': 'jiguang',
            'type': 2,
            'auth': {
                'app_key': '93e1a9f71db4f044de4db34a',
                'master_secret': '5f996ee39c7eb52906510cc2',
                'sign_id': '18138',
                'template_code': {
                    'login': '1',
                    'change': '1',
                    'register': '1',
                }
            },
            'active': True
        },
    ]

}
CACHE_KEY_TEMPLATE = {
    'user_can_download_key': 'user_can_download',
    'download_times_key': 'app_download_times',
    'make_token_key': 'make_token',
    'download_short_key': 'download_short',
    'app_instance_key': 'app_instance',
    'download_url_key': 'download_url',
    'user_storage_key': 'storage_auth',
    'user_auth_token_key': 'user_auth_token',
    'download_today_times_key': 'download_today_times',
    'developer_auth_code_key': 'developer_auth_code',
    'upload_file_tmp_name_key': 'upload_file_tmp_name',
    'login_failed_try_times_key': 'login_failed_try_times',
    'user_free_download_times_key': 'user_free_download_times',
    'super_sign_failed_send_msg_times_key': 'super_sign_failed_send_msg_times'
}

DATA_DOWNLOAD_KEY = "d_token"
FILE_UPLOAD_TMP_KEY = ".tmp"
USER_FREE_DOWNLOAD_TIMES = 20
AUTH_USER_FREE_DOWNLOAD_TIMES = 60

SYNC_CACHE_TO_DATABASE = {
    'download_times': 10,  # 下载次数同步时间
    'try_login_times': (10, 12 * 60 * 60),  # 当天登录失败次数，超过该失败次数，锁定24小时
    'auto_clean_tmp_file_times': 60 * 30,  # 定时清理上传失误生成的临时文件
    'auto_clean_local_tmp_file_times': 60 * 30,  # 定时清理临时文件,现在包含超级签名描述临时文件
    'auto_clean_apscheduler_log': 100000,  # 定时清理定时任务执行的日志,该日志存在数据库中，该参数为日志保留的数量
    'try_send_msg_over_limit_times': (3, 60 * 60),  # 每小时用户发送信息次数
    'clean_local_tmp_file_from_mtime': 60 * 60,  # 清理最后一次修改时间超过限制时间的临时文件,单位秒
    'auto_check_ios_developer_active_times': 60 * 60 * 12,  # ios开发者证书检测时间
}

SERVER_DOMAIN = {
    'IOS_PMFILE_DOWNLOAD_DOMAIN': {
        "domain_name": 'app.hehelucky.cn',
        'is_https': True,
    },  # 验证码，ios 描述文件和plist文件下载域名，该域名用于后端，一般为api访问域名
    'POST_UDID_DOMAIN': 'https://app.hehelucky.cn',  # 超级签名 安装签名时 向该域名 发送udid数据，该域名用于后端，一般为 api 访问域名
    # 'REDIRECT_UDID_DOMAIN': 'https://app.hehelucky.cn',  # 超级签名 安装完成之后，跳转域名，该域名为前端web访问域名，如果用户定义了自己的域名，则跳转用户域名
    'FILE_UPLOAD_DOMAIN': 'https://app.hehelucky.cn',  # 本地文件上传域名，使用本地存储必须配置
}

MOBILECONFIG_SIGN_SSL = {
    # 描述文件是否签名，默认是关闭状态；如果开启，并且ssl_key_path 和 ssl_pem_path 正常，则使用填写的ssl进行签名,否则默认不签名
    'open': False,
    'ssl_key_path': '/data/cert/app.hehelucky.cn.key',
    'ssl_pem_path': '/data/cert/app.hehelucky.cn.pem'
}

DEFAULT_MOBILEPROVISION = {
    # 默认描述文件路径或者下载路径，用户企业签名或者超级签名 跳转 [设置 - 通用 - 描述文件|设备管理] 页面
    # 如果配置了path路径，则走路径，如果配置了url，则走URL，path 优先级大于url优先级
    'enterprise': {
        'path': os.path.join(MEDIA_ROOT, 'embedded.mobileprovision'),
        'url': 'https://ali-static.jappstore.com/embedded.mobileprovision'
    },
    'supersign': {
        # 超级签名，如果self 为True，则默认用自己的描述文件，否则同企业配置顺序一致,自己的配置文件有时候有问题
        'self': False,
        'path': os.path.join(MEDIA_ROOT, 'embedded.mobileprovision'),
        'url': 'https://ali-static.jappstore.com/embedded.mobileprovision'
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

CAPTCHA_TIMEOUT = 5  # Minutes
CAPTCHA_LENGTH = 6  # Chars

BASE_LOG_DIR = os.path.join(BASE_DIR, "logs")
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s][%(threadName)s:%(thread)d][task_id:%(name)s][%(filename)s:%(lineno)d]'
                      '[%(levelname)s][%(message)s]'
        },
        'simple': {
            'format': '[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d]%(message)s'
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'filters': ['require_debug_true'],  # 只有在Django debug为True时才在屏幕打印日志
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'TF': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',  # 保存到文件，根据时间自动切
            'filename': os.path.join(BASE_LOG_DIR, "flyapp_info.log"),  # 日志文件
            'backupCount': 10,  # 备份数为3  xx.log --> xx.log.2018-08-23_00-00-00 --> xx.log.2018-08-24_00-00-00 --> ...
            'when': 'D',  # 每天一切， 可选值有S/秒 M/分 H/小时 D/天 W0-W6/周(0=周一) midnight/如果没指定时间就默认在午夜
            'formatter': 'standard',
            'encoding': 'utf-8',
        },
        'error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',  # 保存到文件，自动切
            'filename': os.path.join(BASE_LOG_DIR, "flyapp_err.log"),  # 日志文件
            'maxBytes': 1024 * 1024 * 5,  # 日志大小 50M
            'backupCount': 10,
            'formatter': 'standard',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        '': {  # 默认的logger应用如下配置
            'handlers': ['TF', 'console', 'error'],  # 上线之后可以把'console'移除
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

PAY_SUCCESS_URL = 'https://app.hehelucky.cn/user/orders'  # 前端页面，支付成功跳转页面
PAY_CONFIG = [
    {
        'NAME': 'alipay',
        'TYPE': 'ALI',
        'ENABLED': True,
        'AUTH': {
            'APP_ID': "2021002138691845",
            'APP_PRIVATE_KEY': '''-----BEGIN RSA PRIVATE KEY-----
    MIIEowIBAAKCAQEAhqf2mwftoxZDNpl4eWsQ6mEfXgMlNPr6jv72ecA4hbKWqChXQmGS1T+0VsRTSoOXRDlu1MMqkTGISzHvmGb7Gmw+Myfs/ojoonD9r8fODvIo1MHolFBhr3GNQu7tqBlVJ76QgiYft+c4kkqCguuyCrd3Te6C5zCIuh6O98r4D3A3LFcm6OdScWGcfEbR+FUv+jSi2oezHeSpkhhpHGBLSsI0L9JOdHetdUE/TwN8V1HABdpnPXtp9SIu6ioIrrligX1ZRlwht2YUt0BPqPp/ApLdRIsqlhD4/ejmtMlaRqqiN6PulEThBew/qaLVSXIr2HCSXtwbki3pFMFOcsjF2wIDAQABAoIBADp4sQL83FnXDvSki8XdkgjUh7RhFUT+PtLdL9YKfADCXd1DNzDiAcqL0RlkQu62WXcMoW3OGavWoGJWmr3I6fy9R/0atzSH6syu19n+nyGqUcShNwdAKErwufB4o8Y8yddqToHVYCyRQOV1aVrEUhmJNUsn6LvPPW/kWRyMjE7XQDFHpL5/Ly7pXe+f9Btm37ZuePTPsm65P88C3GznjZxXhY1LBWFKLPG1470xdReduyeJFZS/TmK0nUxLwkACm9Gfvp7S2KJ3okUXohsGBAgJ68B9YeGiuIJiZhH2DZ1pm3/R9bSpOX3H+6vjaCsacXT5w7LZB+O0Vkthcm9vqeECgYEAvozFkIkFXXCEmCr3QVCJs4Fc6onbXEJU45xxubPhkA1wwwPrSqdubo4RHvNIus45Fn4mLzuQsaPRyJJZajvaKWC00GxhChMYj+nWgkAmABPKGwkMxzjC7wvEJkGyt87fHpK1XMFWQgfJ42VwUtmyemCMuh+A2SOekIJay93xTtkCgYEAtOhmQ4pu2cyqTzT+SD7p/VnS4sNqqM4I8NSvTuLkEo2IHnUj7YG6XoPZjn35dBvYUWWN2dwgfHXGEEzCOIwfy8GPA4eoKCDNEkMvoBVLdrEzMqg5QwG5GsIGvOuFnAzAw+D5YwEym/qmC2oBbat5jsAGT2rMmU5MnaS8a7lvcdMCgYEAiusQQb5TZfrZACMa3cg8i9y9A9R7UzicsM/mbW+B+8aAtfxOdr+4F+uE+d594IrmPcq8ReUUKR34nFRt0bBO7amuSOEqofCoEIt3MsBXs+i5iJpBcaClJSeb2hQ9mhm8uopUpInjPAJ3okva5twFbYikMDE1e5inSk1uqoBlI4kCgYB4rzDJjeg1U9upy2h3OcFPSkTtEgBtbEV6o+fvcF1GIzTTXMIDB7AUrVDNRizL0GeWpXDkDX1+ifL/nLVUk+YCP7XwXOdJHdiwfjGfUZVuMPg+qwrIMLYTq6xjC5uuZrOR+NtluL7SX3u10ZnyV5pYKLIM+OpUu29RGzy3gJVgEQKBgCC9vXS7P9RHTAxYEG4WOzv0tjFUtPOsaHenvNbc7nVe2Kkre0/TO+EtnuhINmJp2y5UEve6cLK2sPnbT8raarjPuomDfN0hwEx3jZd+rPdB/tdRH0LMLBu28TlzHllJYjbINn+NXc0adbqeuA4ziXTZow5yX5J+i9dy55A1bvie
    -----END RSA PRIVATE KEY-----''',
            'ALI_PUBLIC_KEY': '''-----BEGIN CERTIFICATE-----
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAkru1ulQV1v4q+q38nyzgkdd3evf7C1/Ipu6K+ZFb5FiuxJ7mildkBSuKz/8+TRd+tjgk2lfc2ehK5pja3cxDO/nb25sBoWiU09rtxgXLehLsgRRhatbICrlOnYxg5aiB5odAp3NMRqore4lnVYwfIyL9M49I0G/NbQzYjUQvAQJsnHwc6a6Kuqi1CwR1WXI0sDF9w7KXC4vRFFIUTwI4bVq4HQWI7NhbgEajHM/j6D6Bh/OMcTYnJJzCja0WmZRe5flfCsELlPESOCWUMbYoaNfBzpNvvyOpmRgs9jgy2WY9SeaB9hxwkpr8tOd2Sc7j3221JKCyDaFAX+4zPy7/fQIDAQAB
    -----END CERTIFICATE-----''',
            'APP_NOTIFY_URL': 'https://app.hehelucky.cn/api/v1/fir/server/pay_success',  # 支付支付回调URL
            'RETURN_URL': PAY_SUCCESS_URL,  # 支付前端页面回调URL
            'SUBJECT': '向 FLY分发平台 充值',
        }
    },
    {
        'TYPE': 'WX',
        'NAME': 'wxpay',
        'ENABLED': True,
        'AUTH': {
            'APP_ID': "wx390e5985fd3699e6",
            'MCH_ID': "1608486112",
            'SERIAL_NO': "27DADA4D2921CDD66B8B20A68276F09B90754922",
            'APP_PRIVATE_KEY': '''-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDbXhNoHljrkS8T
jXg3+tTkaoOol8FDt0jSGckhzX46gkS16CWYwTthBKurfFtynsJe4uDOphS1ge/r
QEU3+rWNxqa8o6gHSpp2UTYAz/1oYOlXuSa4NA1uD47lmVZJzad2ybWDSsoeRjFj
c+X6F0ZiE3FmdN1iHz8NmbP99foih4smv15X+wX5DrsuLuPVHNB4D0fqvY7P5PO3
wUQXWQNezCYzpPoXX2H/UkyFEFZhWk6/9z3aAkYmqfd6IWPHewOqnVoQRKmo5bXb
yWbB+QIl/HcSfNtq869s5lLGR2Rl2UX8IFXCcXnRPhSAVIeWfXN26Pc9dz9N4VTU
yiZ8Y6AHAgMBAAECggEABdS0U1orJufPBogGIAbMzd1+7mZKPtCKYPtKe1mI92kr
BmLLTQol1+hV39MIYz2RERCaxSNo/YIcrHYi4OALH1+eYvk+qCL1hBuYgeEFbVbW
HPzQ6KiJitljBPtUbdXHk8K8zmaYhMF84pXcEQ+5UTYPF5gXoloORQBG5oM5SN2g
2GTgYw1cpDzzRRwnmpvYd1ZydYNj8m6k7I2L1pwzRS/6/whz1sScpfh+91w1IVM0
WT+pPSdiVtQ7ktmvcTrWj7eNIbcsptZ1QgSV3UHkU0xzLG9N1TqJdHOquunXRS7V
iw/4NgXveXSTSQrmmZVS+Kdyc+z1iDqwOXmE7hjioQKBgQD7js+40NCAPLYXEfer
UFvZ6kem9mJIzAUdeTdK4BjYJrcU+UsXRmcWJIPI9HWSr31f/fSfu2SKyBa6+dFF
SeNHuHPPqQAXrsNuhFG1wcKoNybk7KrsQlXheK7br42565Tegz3UXOKMrnPPlukH
ZZdlYmwBFjEJvIr9jxJvJoW6qQKBgQDfPb697vR8ruLaecPmsq920iC3AQRanYFK
dW6U98JkCN9A/LXA1jGyDTEhtlja+5Ylp0M1EnlcZ079Jnvek5haSNnD0xb1nMy8
P/o0/eWWArTgfjfiJeq1tSdrinGhNz0+Vty74wnbS+5P18H23I5jBlGX5hyNkU4L
axUfJM9jLwKBgCo/1xVkRNB04eRICT/FlFeqKHSbRvCRC37iv+2ca6/J+M/V+s2i
7mdipJuYqzKCtNztayt0rrM8Xczzbjlj6n8+NH05FiHkIUCriomrTEUyVh72vNJH
ZeMjgMK23mfOcEda5YSIQSh9mEfSQbsTTfUiLZ+VGZFYEEP7xo3Se31ZAoGBAJas
LPYytq8EtrYwowktJwJydoQt2otybRYdRmKjCn/MASrypZWeu/Hpt3SCh1xdnAyT
5OeILYMxcv2noMksIxMkwl3KNl/V0dVo9O4ZQ4DJGN3AMuWfI9g6iX2q9mCSUPKn
W9owNbHegN1AyXhdinjJhf6Y4EKohN1uC9Z2WMcfAoGAW90Z2LkqG2fen+R62syP
aaInnu9bitb9rVENCNGXQHdWmIYBMM5zrg8nX8xNJ+yeGQhgxE+YeSq4FOpe0JkA
daWIhg++OHN2MBRutj7oL/AFAxyu467YA5+itEJLHNATbOr/s13S66nePNXox/hr
bIX1aWjPxirQX9mzaL3oEQI=
-----END PRIVATE KEY-----''',
            'API_V3_KEY': '60DbP621a9C3162dDd4AB9c2O15a005L',
            'APP_NOTIFY_URL': 'https://app.hehelucky.cn/api/v1/fir/server/pay_success',  # 支付支付回调URL
            'RETURN_URL': PAY_SUCCESS_URL,  # 支付前端页面回调URL
            'SUBJECT': '向 FLY分发平台 充值',
        }
    }
]

# 结果存放到Django|redis
# CELERY_RESULT_BACKEND = 'django-db'
# CELERY_RESULT_BACKEND = 'django-cache'
# result_backend = 'redis://username:password@host:port/db'
# result_backend = 'redis://:password@host:port/db'
CELERY_RESULT_BACKEND = 'django-db'
# CELERY_RESULT_BACKEND = 'db+sqlite:///results.sqlite'


# broker redis|mq
DJANGO_DEFAULT_CACHES = CACHES['default']
CELERY_BROKER_URL = 'redis://:%s@%s/2' % (
    DJANGO_DEFAULT_CACHES["OPTIONS"]["PASSWORD"], DJANGO_DEFAULT_CACHES["LOCATION"].split("/")[2])
# CELERY_BROKER_URL = 'amqp://guest@localhost//'
#: Only add pickle to this list if your broker is secured


CELERYD_CONCURRENCY = 4  # worker并发数
CELERYD_FORCE_EXECV = True  # 非常重要,有些情况下可以防止死
CELERY_TASK_RESULT_EXPIRES = 3600  # 任务结果过期时间

CELERY_DISABLE_RATE_LIMITS = True  # 任务发出后，经过一段时间还未收到acknowledge , 就将任务重新交给其他worker执行
CELERYD_PREFETCH_MULTIPLIER = 3  # celery worker 每次去redis取任务的数量

CELERYD_MAX_TASKS_PER_CHILD = 200  # 每个worker执行了多少任务就会死掉，我建议数量可以大一些，比如200

# CELERYD_WORKER_PREFETCH_MULTIPLIER  =1

CELERY_ENABLE_UTC = False
DJANGO_CELERY_BEAT_TZ_AWARE = False
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

CELERY_BEAT_SCHEDULE = {
    'sync_download_times_job': {
        'task': 'api.tasks.sync_download_times_job',
        'schedule': SYNC_CACHE_TO_DATABASE.get("download_times"),
        'args': ()
    },
    'check_bypass_status_job': {
        'task': 'api.tasks.check_bypass_status_job',
        'schedule': GEETEST_CYCLE_TIME,
        'args': ()
    },
    'auto_clean_upload_tmp_file_job': {
        'task': 'api.tasks.auto_clean_upload_tmp_file_job',
        'schedule': SYNC_CACHE_TO_DATABASE.get("auto_clean_tmp_file_times"),
        'args': ()
    },
    'auto_delete_tmp_file_job': {
        'task': 'api.tasks.auto_delete_tmp_file_job',
        'schedule': SYNC_CACHE_TO_DATABASE.get("auto_clean_local_tmp_file_times"),
        'args': ()
    },
    'auto_check_ios_developer_active_job': {
        'task': 'api.tasks.auto_check_ios_developer_active_job',
        'schedule': SYNC_CACHE_TO_DATABASE.get("auto_check_ios_developer_active_times"),
        'args': ()
    },
    'start_api_sever_do_clean': {
        'task': 'api.tasks.start_api_sever_do_clean',
        'schedule': 6,
        'args': (),
        'one_off': True
    },
}

MSGTEMPLATE = {
    'NOT_EXIST_DEVELOPER': '用户 %s 你好，应用 %s 签名失败了，苹果开发者总设备量已经超限，请添加新的苹果开发者或者修改开发者设备数量。感谢有你!',
    'ERROR_DEVELOPER': '用户 %s 你好，应用 %s 签名失败了，苹果开发者 %s 信息异常，请重新检查苹果开发者状态是否正常。感谢有你!',
    'AUTO_CHECK_DEVELOPER': '用户 %s 你好，苹果开发者 %s 信息异常，请重新检查苹果开发者状态是否正常。感谢有你!',
}
