from django.conf.urls.defaults import *

urlpatterns = patterns('',
    (r'^upload/', 'webit.bitinfo.views.upload_torrent'),
    #(r'^webit/', include('webit.foo.urls')),

    # Uncomment this for admin:
#     (r'^admin/', include('django.contrib.admin.urls')),
)
