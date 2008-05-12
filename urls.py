from django.conf.urls.defaults import *

urlpatterns = patterns('',
                       
    (r'^d/(?P<torrent>[^/]+)/(?P<index>.+).part', 'webit.bitdownload.views.get_data'),
                       
    (r'^upload/', 'webit.bitinfo.views.upload_torrent'),
    #(r'^webit/', include('webit.foo.urls')),

    # Uncomment this for admin:
#     (r'^admin/', include('django.contrib.admin.urls')),
)
