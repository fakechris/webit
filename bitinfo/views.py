#coding:utf-8

import time
from sha import *

from BTL.bencode import *

from django.conf import settings

from django import newforms as forms

from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext, loader, Context, Template

from webit.bitinfo.models import *

class TorrentForm(forms.ModelForm):
    """
    This class represents torrent upload form
    """
    class Meta:
        model = Torrent

def upload_torrent(request):
    """
    upload torrent file to show info
    
    request -- 
    """
    
    if request.method == "POST":
        #print request.POST, request.FILES
        form = TorrentForm(request.POST, request.FILES)        
        if form.is_valid():
            torrent = form.save(commit=False)
            #print torrent.filename
            return torrent_info(request, torrent.filename)
    else:
        form = TorrentForm()
    return render_to_response('bitinfo/upload_torrent.html',
            {
                'form' : form,
            },
            RequestContext(request) )

def torrent_info(request, filename):
    metaname = settings.MEDIA_ROOT + filename
    metafile = open(metaname, "rb")
    metainfo = bdecode(metafile.read())
    metafile.close()

    info = metainfo['info']
    info_hash = sha(bencode(info)).hexdigest()
    
    title = metainfo.get('title', '')
    #filename
    piece_length = info['piece length']
    if info.has_key('length'):
        # single file mode
        path_name = ''
        files = [ { 'fname':info['name'],
            'length':info['length'],
            'content_type':info.get('content_type','')
            }, ]
        file_length = info['length']
    else:
        # multiple files mode        
        path_name = info['name']
        files = []
        file_length = 0
        for file in info['files']:
            path = "/".join( file["path"] )
            files.append( { 'fname':path,
                            'length':file['length'],
                            'content_type':file.get('content_type',''), } )
            file_length += file['length']

    piece_number, last_piece_length = divmod(file_length, piece_length)
    announce = metainfo.get('announce','')
    announce_list = metainfo.get('announce-list','')
    nodes = map(lambda n:{'ip':n[0], 'port':n[1]}, metainfo['nodes'])
    comment = metainfo.get('comment','')
    url_list = metainfo.get('url-list', '')

    create_date = time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime(metainfo.get('creation date', 0)))

    return render_to_response('bitinfo/torrent_info.html',
            locals(),
            RequestContext(request) )




