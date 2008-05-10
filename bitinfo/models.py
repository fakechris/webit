#coding:utf-8

from django.db import models

class Torrent(models.Model):
    filename = models.FileField(upload_to="torrent")
    path = models.CharField(max_length=255,default='',blank=True)

    #def save(self):
    #    pass

