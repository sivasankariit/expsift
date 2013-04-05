# Django settings for expsift project.

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
    # ('Your Name', 'your_email@example.com'),
)

MANAGERS = ADMINS

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.', # Add 'postgresql_psycopg2', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': '',                      # Or path to database file if using sqlite3.
        'USER': '',                      # Not used with sqlite3.
        'PASSWORD': '',                  # Not used with sqlite3.
        'HOST': '',                      # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                      # Set to empty string for default. Not used with sqlite3.
    }
}

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# On Unix systems, a value of None will cause Django to use the same
# timezone as the operating system.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'America/Los_Angeles'

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = True

# If you set this to False, Django will not format dates, numbers and
# calendars according to the current locale.
USE_L10N = True

# If you set this to False, Django will not use timezone-aware datetimes.
USE_TZ = True

# Absolute filesystem path to the directory that will hold user-uploaded files.
# Example: "/home/media/media.lawrence.com/media/"
MEDIA_ROOT = ''

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash.
# Examples: "http://media.lawrence.com/media/", "http://example.com/media/"
MEDIA_URL = ''

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/home/media/media.lawrence.com/static/"
STATIC_ROOT = ''

# URL prefix for static files.
# Example: "http://media.lawrence.com/static/"
STATIC_URL = '/static/'

# Additional locations of static files
STATICFILES_DIRS = (
    # Put strings here, like "/home/html/static" or "C:/www/django/static".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

# List of finder classes that know how to find static files in
# various locations.
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
#    'django.contrib.staticfiles.finders.DefaultStorageFinder',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'nc1&amp;(x2zh7$clai+$qz!f!1ddc=_5tg29mjs6_88(q#en-s@%q'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.Loader',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Uncomment the next line for simple clickjacking protection:
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'expsift.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'expsift.wsgi.application'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.

    # Expsift: Include the absolute path to the expsift template directory here
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Uncomment the next line to enable the admin:
    # 'django.contrib.admin',
    # Uncomment the next line to enable admin documentation:
    # 'django.contrib.admindocs',
    'expsift'
)

# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        }
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
    }
}

# Expsift: Redis key-value store settings
REDIS_DB = {
    'host' : 'localhost',
    'port' : 6379,
}

# Expsift: Maximum lengths of tags and comments files that will be read
# Set negative values for these parameters to not restrict the lengths of the
# files that are read while returning the results. Warning: If the files are
# long, it might take a long time to read them.
# These restrictions do not apply while writing the values to the files.
MAX_EXPSIFT_TAGS_FILE_SIZE = 102400 #100KB
MAX_EXPSIFT_COMMENTS_FILE_SIZE = 102400 #100KB

# Expsift: Experiment logs
# Absolute path to experiment logs root directory. Configure Apache to serve
# files in this directory at django-site/expt-logs/. Any experiment directories
# in the redis database which are not inside this directory are ignored.
# Max length of displayed directory names. Longer directory names are
# truncated.
EXPT_LOGS = {
    'directory' : '',
    'max_dir_length' : 50,
}

# Expsift: Comparison functions for multiple directories
# The key in this dictionary is the name of the operation (which will be
# displayed in the homepage)
# The value is a dictionary that specifies the module_name and method_name that
# will be called to execute the operation. The module should be available in
# PYTHON_PATH
#
# All comparison methods specified should return django.http.HttpResponse
# objects.
#
# If this dictionary is empty, then no comparison operation is available.
COMPARE_FUNCTIONS = {
    #'Compare Operation' : {
    #    'module_name' : '',
    #    'method_name' : ''
    #},
}

# Expsift: Function to display individual experiment directory info
#
# The dictionary specifies the module_name and method_name that will be called
# to display the experiment info. The module should be available in PYTHON_PATH
#
# The method specified should return a django.http.HttpResponse object.
#
# If these values are not configured, then the default individual experiment
# page is displayed.
INDIVIDUAL_EXPT_PAGE_FUNC = {
    'module_name' : 'individual_plot_www',
    'method_name' : 'individual_plot',
}
