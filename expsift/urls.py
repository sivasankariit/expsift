from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    url(r'^$', 'expsift.views.home', name='home'),
    url(r'^filter/$', 'expsift.views.filter', name='filter'),
    url(r'^update_expts/$', 'expsift.views.update_expts', name='update_expts'),
    url(r'^compare_expts/$', 'expsift.views.compare_expts_base',
        name='compare_expts'),
    url(r'^show_expt_directories/$', 'expsift.views.show_expt_directories',
        name='show_expt_dirs'),
    # url(r'^expsift/', include('expsift.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)
