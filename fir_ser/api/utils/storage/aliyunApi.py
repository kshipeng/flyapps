#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 3月
# author: liuyu
# date: 2020/3/22

# pip install aliyun-python-sdk-sts oss2

import json
import os

from aliyunsdkcore import client
from aliyunsdksts.request.v20150401 import AssumeRoleRequest

import oss2


# 以下代码展示了STS的用法，包括角色扮演获取临时用户的密钥、使用临时用户的密钥访问OSS。

# STS入门教程请参看  https://yq.aliyun.com/articles/57895
# STS的官方文档请参看  https://help.aliyun.com/document_detail/28627.html

# 首先初始化AccessKeyId、AccessKeySecret、Endpoint等信息。
# 通过环境变量获取，或者把诸如“<你的AccessKeyId>”替换成真实的AccessKeyId等。
# 注意：AccessKeyId、AccessKeySecret为子用户的密钥。
# 子用户需要有  调用STS服务AssumeRole接口的权限
# 创建ram用户，授权 管理对象存储服务（OSS）权限
# RoleArn可以在控制台的“访问控制  > RAM角色管理  > 创建的ram用户  > 基本信息  > Arn”上查看。
#
# 以杭州区域为例，Endpoint可以是：
#   http://oss-cn-hangzhou.aliyuncs.com
#   https://oss-cn-hangzhou.aliyuncs.com
# 分别以HTTP、HTTPS协议访问。

class StsToken(object):
    """AssumeRole返回的临时用户密钥
    :param str access_key_id: 临时用户的access key id
    :param str access_key_secret: 临时用户的access key secret
    :param int expiration: 过期时间，UNIX时间，自1970年1月1日UTC零点的秒数
    :param str security_token: 临时用户Token
    :param str request_id: 请求ID
    """

    def __init__(self):
        self.access_key_id = ''
        self.access_key_secret = ''
        self.expiration = 3600
        self.security_token = ''
        self.request_id = ''
        self.bucket = ''
        self.endpoint = ''


class AliYunOss(object):

    def __init__(self, access_key, secret_key, bucket_name, endpoint, sts_role_arn, is_https, domain_name=None):
        self.access_key_id = access_key or os.getenv('OSS_TEST_STS_ID', 'LTAI4FeTyvz74CHKCbYuTDGc')
        self.access_key_secret = secret_key or os.getenv('OSS_TEST_STS_KEY', 'uineAEE7tp1d1w4Mv0yLqxvV0IVNTy')
        self.bucket_name = bucket_name or os.getenv('OSS_TEST_BUCKET', 'fir-storage')
        self.endpoint = endpoint or os.getenv('OSS_TEST_ENDPOINT', 'oss-cn-beijing.aliyuncs.com')
        self.sts_role_arn = sts_role_arn or os.getenv('OSS_TEST_STS_ARN', 'acs:ram::1622120977387033:role/appstorage')
        self.region_id = '-'.join(self.endpoint.split('.')[0].split("-")[1:3])
        self.token = StsToken()
        self.is_https = is_https
        self.domain_name = domain_name
        self.get_auth_bucket('init', 900)

    def fetch_sts_token(self, name, expires):
        """子用户角色扮演获取临时用户的密钥
        :param access_key_id: 子用户的 access key id
        :param access_key_secret: 子用户的 access key secret
        :param role_arn: STS角色的Arn
        :return StsToken: 临时用户密钥
        """
        clt = client.AcsClient(self.access_key_id, self.access_key_secret, self.region_id)
        req = AssumeRoleRequest.AssumeRoleRequest()

        req.set_accept_format('json')
        req.set_RoleArn(self.sts_role_arn)
        req.set_RoleSessionName(name[0:31])
        req.set_DurationSeconds(expires)

        body = clt.do_action_with_exception(req)

        j = json.loads(oss2.to_unicode(body))

        self.token.access_key_id = j['Credentials']['AccessKeyId']
        self.token.access_key_secret = j['Credentials']['AccessKeySecret']
        self.token.security_token = j['Credentials']['SecurityToken']
        self.token.request_id = j['RequestId']
        self.token.expiration = oss2.utils.to_unixtime(j['Credentials']['Expiration'], '%Y-%m-%dT%H:%M:%SZ')
        self.token.bucket = self.bucket_name
        self.token.endpoint = self.endpoint
        return self.token.__dict__

    def get_upload_token(self, name, expires=1800):
        return self.fetch_sts_token(name, expires)

    def get_auth_bucket(self, name, expires):
        self.fetch_sts_token(name, expires)
        uri = 'http://'
        if self.is_https:
            uri = 'https://'
        url = self.endpoint
        is_cname = False
        if self.domain_name:
            url = self.domain_name
            is_cname = True

        auth = oss2.StsAuth(self.token.access_key_id, self.token.access_key_secret, self.token.security_token)
        self.bucket = oss2.Bucket(auth, uri + url, self.bucket_name, is_cname=is_cname)

    def get_download_url(self, name, expires=1800, force_new=False):
        # self.get_auth_bucket(name,expires)
        private_url = self.bucket.sign_url('GET', name, expires)
        return private_url

    def del_file(self, name):
        # self.fetch_sts_token(name,expires=300)
        # auth = oss2.StsAuth(self.token.access_key_id, self.token.access_key_secret, self.token.security_token)
        # bucket = oss2.Bucket(auth, self.endpoint,self.bucket_name)
        return self.bucket.delete_object(name)

    def rename_file(self, oldfilename, newfilename):
        self.bucket.copy_object(self.bucket_name, oldfilename, newfilename)
        return self.del_file(oldfilename)

    def upload_file(self, local_file_full_path):
        if os.path.isfile(local_file_full_path):
            self.bucket.put_object_from_file(os.path.basename(local_file_full_path), local_file_full_path)
            # with open(local_file_full_path, 'rb') as fileobj:
            #     # Seek方法用于指定从第1000个字节位置开始读写。上传时会从您指定的第1000个字节位置开始上传，直到文件结束。
            #     fileobj.seek(1000, os.SEEK_SET)
            #     # Tell方法用于返回当前位置。
            #     # current = fileobj.tell()
            #     self.bucket.put_object(os.path.basename(local_file_full_path), fileobj)
            return True
