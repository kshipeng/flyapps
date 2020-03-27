#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 3月 
# author: liuyu
# date: 2020/3/6
from rest_framework.views import APIView
from api.utils.response import BaseResponse
from rest_framework.response import Response
from fir_ser import settings
from api.utils.TokenManager import DownloadToken
from api.utils.app.randomstrings import make_random_uuid
from api.utils.app.apputils import make_resigned
from api.utils.storage.storage import Storage
import os

from api.utils.serializer import AppsSerializer
from api.models import Apps,AppReleaseInfo
from django.http import FileResponse
class DownloadView(APIView):
    '''
    文件下载接口,适用于本地存储和所有plist文件下载
    '''
    # authentication_classes = [ExpiringTokenAuthentication, ]
    # parser_classes = (MultiPartParser,)

    def get(self,request,filename):
        res = BaseResponse()
        downtoken = request.query_params.get("token", None)
        ftype = request.query_params.get("ftype",None)
        if not downtoken:
            res.code=1004
            res.msg="缺失token"
            return Response(res.dict)

        dtoken = DownloadToken()
        if dtoken.verify_token(downtoken,filename):
            if not ftype:
                file_path = os.path.join(settings.MEDIA_ROOT, filename)
                try:
                    response = FileResponse(open(file_path, 'rb'))
                except Exception as e:
                    print(e)
                    response = FileResponse()
                response['content_type'] = "application/octet-stream"
                response['Content-Disposition'] = 'attachment; filename=' + filename
                return response
            else:
                if ftype == 'plist':
                    release_obj = AppReleaseInfo.objects.filter(release_id=filename.split('.')[0]).first()
                    if release_obj:
                        storage = Storage(release_obj.app_id.user_id)
                        bundle_id = release_obj.app_id.bundle_id
                        app_version = release_obj.app_version
                        name = release_obj.app_id.name
                        ios_plist_bytes = make_resigned(storage.get_download_url(filename),storage.get_download_url(release_obj.icon_url),bundle_id,app_version,name)
                        response = FileResponse(ios_plist_bytes)
                        response['content_type'] = "application/x-plist"
                        response['Content-Disposition'] = 'attachment; filename=' + make_random_uuid()
                        return response

        res.code=1004
        res.msg="token校验失败"
        return Response(res.dict)



class ShortDownloadView(APIView):
    '''
    根据下载短链接，获取应用信息
    '''

    def get(self,request,short):
        res = BaseResponse()
        release_id = request.query_params.get("release_id", None)
        app_obj = Apps.objects.filter(short=short).first()
        if not app_obj:
            res.code=1003
            res.msg="该应用不存在"
            return Response(res.dict)

        app_serializer = AppsSerializer(app_obj,context={"release_id":release_id,"storage":Storage(app_obj.user_id)})
        res.data = app_serializer.data
        return Response(res.dict)


class InstallView(APIView):
    '''
    安装操作，前端通过token 认证，认证成功之后，返回 下载连接，并且 让下载次数加一
    '''

    def get(self,request,app_id):
        res = BaseResponse()
        downtoken = request.query_params.get("token", None)
        short = request.query_params.get("short",None)
        release_id = request.query_params.get("release_id",None)
        isdownload = request.query_params.get("isdownload",None)

        if not downtoken or not short or not release_id:
            res.code=1004
            res.msg="参数丢失"
            return Response(res.dict)

        dtoken = DownloadToken()
        if dtoken.verify_token(downtoken,release_id):
            app_obj = Apps.objects.filter(app_id=app_id,short=short).first()
            if app_obj:

                app_obj.count_hits = app_obj.count_hits+1
                app_obj.save()
                app_obj.user_id.all_download_times = app_obj.user_id.all_download_times+1
                app_obj.user_id.save()

                release_obj = AppReleaseInfo.objects.filter(app_id=app_obj,release_id=release_id).first()
                if release_obj:
                    storage = Storage(app_obj.user_id)
                    if app_obj.type == 0:
                        apptype = '.apk'
                        download_url = storage.get_download_url(release_obj.release_id + apptype,600)
                    else:
                        apptype = '.ipa'
                        if isdownload :
                            download_url = storage.get_download_url(release_obj.release_id + apptype, 600)
                        else:
                            download_url = storage.get_download_url(release_obj.release_id + apptype,600,'plist')

                    res.data={"download_url":download_url}
                    return Response(res.dict)
        else:
            res.code = 1004
            res.msg = "token校验失败"
            return Response(res.dict)

        res.code = 1006
        res.msg = "该应用不存在"
        return Response(res.dict)
