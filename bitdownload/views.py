# Create your views here.

from django.conf import settings
from django.http import HttpResponse, Http404

from webit.btl.storage import StorageManage

def get_data(request, torrent, index):
    # TODO: caching meta data
    torrent_file = settings.MEDIA_ROOT + "torrent/" + torrent
    data_path = settings.MEDIA_ROOT + "data/" + torrent + "/"
    sm = StorageManage(torrent_file, data_path)
    r = sm.read(index * sm.metainfo.piece_length, sm.metainfo.piece_length)
    return HttpResponse(r, mimetype="application/octet-stream")
    


