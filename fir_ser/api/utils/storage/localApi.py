#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 3月 
# author: liuyu
# date: 2020/3/18
'''
本地存储api
'''
from api.utils.TokenManager import DownloadToken
from fir_ser import settings
import os


class LocalStorage(object):
    def __init__(self, domain_name, is_https):
        self.domain_name = domain_name
        self.is_https = is_https

    def get_upload_token(self, name, expires):
        dtoken = DownloadToken()
        return dtoken.make_token(name, expires)

    def get_base_url(self):
        uri = 'http://'
        if self.is_https:
            uri = 'https://'
        return "%s%s" % (uri, self.domain_name)

    def get_download_url(self, name, expires=600, force_new=False):
        dtoken = DownloadToken()
        download_url = '/'.join([self.get_base_url(), 'download', name])
        if settings.DATA_DOWNLOAD_KEY_OPEN:
            download_url = "%s?%s=%s" % (
                download_url, settings.DATA_DOWNLOAD_KEY, dtoken.make_token(name, expires, force_new=force_new))
        return download_url

    def del_file(self, name):
        try:
            file = os.path.join(settings.MEDIA_ROOT, name)
            if os.path.isfile(file):
                os.remove(file)
            return True
        except Exception as e:
            print(e)
            return False

    def rename_file(self, oldfilename, newfilename):
        try:
            os.rename(os.path.join(settings.MEDIA_ROOT, oldfilename), os.path.join(settings.MEDIA_ROOT, newfilename))
            return True
        except Exception as e:
            print(e)
            return False
