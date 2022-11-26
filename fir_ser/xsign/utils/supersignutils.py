#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 3月 
# author: liuyu
# date: 2020/3/6

import logging
import os
import time
import uuid
import zipfile
from io import BytesIO
from wsgiref.util import FileWrapper

import xmltodict
from django.core.cache import cache
from django.db.models import Count, F

from api.models import UserInfo, AppReleaseInfo, Apps
from api.utils.modelutils import get_user_storage_obj
from api.utils.response import BaseResponse
from api.utils.utils import delete_local_files, download_files_form_oss
from common.base.baseutils import file_format_path, delete_app_profile_file, get_profile_full_path, format_apple_date, \
    get_format_time, make_app_uuid, make_from_user_uuid, AesBaseCrypt
from common.base.magic import run_function_by_locker, call_function_try_attempts, magic_wrapper, MagicCacheData
from common.cache.state import CleanErrorBundleIdSignDataState
from common.cache.storage import RedisCacheBase
from common.constants import DeviceStatus, AppleDeveloperStatus, SignStatus
from common.core.sysconfig import Config, UserConfig
from common.notify.notify import sign_failed_notify, sign_unavailable_developer_notify, sign_app_over_limit_notify
from common.utils.caches import del_cache_response_by_short, send_msg_over_limit, check_app_permission, \
    consume_user_download_times_by_app_obj, add_udid_cache_queue, get_and_clean_udid_cache_queue
from common.utils.storage import Storage
from fir_ser.settings import SUPER_SIGN_ROOT, MEDIA_ROOT
from xsign.models import APPSuperSignUsedInfo, AppUDID, AppIOSDeveloperInfo, APPToDeveloper, \
    UDIDsyncDeveloper, DeveloperAppID, DeveloperDevicesID, IosDeveloperPublicPoolBill, AppleDeveloperToAppUse, \
    IosDeveloperBill, DeviceAbnormalUDID, DeviceBlackUDID
from xsign.utils.iossignapi import ResignApp, AppDeveloperApiV2
from xsign.utils.modelutils import get_ios_developer_public_num, check_ipa_is_latest_sign, \
    update_or_create_developer_udid_info, check_uid_has_relevant, get_developer_udided, add_sign_message, \
    update_or_create_abnormal_device
from xsign.utils.serializer import BillAppInfoSerializer, BillDeveloperInfoSerializer
from xsign.utils.utils import delete_app_to_dev_and_file

logger = logging.getLogger(__name__)


def get_sign_oss_storage(user_obj):
    storage_obj = get_user_storage_obj(user_obj)
    if storage_obj.storage_type == 2:
        storage_obj.download_auth_type = 2
        oss_storage_obj = Storage(user_obj, storage_obj, prefix='super_sign')
    else:
        oss_storage_obj = Storage(user_obj, prefix='super_sign')
    return oss_storage_obj


def check_org_file(user_obj, org_file):
    if not os.path.isdir(os.path.dirname(org_file)):
        os.makedirs(os.path.dirname(org_file))

    if os.path.isfile(org_file):
        return True

    return download_files_form_oss(get_sign_oss_storage(user_obj), org_file)


def get_abnormal_queryset(user_obj, udid):
    return DeviceAbnormalUDID.objects.filter(user_id=user_obj,
                                             udid__udid=udid,
                                             udid__developerid__status__in=Config.DEVELOPER_USE_STATUS)


def check_user_udid_black(user_obj, udid):
    if DeviceBlackUDID.objects.filter(user_id=user_obj, udid=udid, enable=True).count():
        return True


def get_developer_queryset_by_udidsync(user_obj, udid, status_list):
    return AppIOSDeveloperInfo.objects.filter(user_id=user_obj,
                                              status__in=Config.DEVELOPER_USE_STATUS,
                                              certid__isnull=False,
                                              udidsyncdeveloper__udid=udid,
                                              udidsyncdeveloper__status__in=status_list)


def check_udid_black(user_obj, udid):
    if check_user_udid_black(user_obj, udid):
        return True
    if UserConfig(user_obj).DEVELOPER_WAIT_ABNORMAL_DEVICE:
        if get_abnormal_queryset(user_obj, udid).filter(auto_remove=False).count():
            return True

        if get_developer_queryset_by_udidsync(user_obj, udid, [DeviceStatus.ENABLED, DeviceStatus.DISABLED]).count():
            get_abnormal_queryset(user_obj, udid).delete()
            return False

        for developer_obj in get_developer_queryset_by_udidsync(user_obj, udid,
                                                                [DeviceStatus.PROCESSING, DeviceStatus.INELIGIBLE]):
            IosUtils.get_device_from_developer(developer_obj)
        return get_abnormal_queryset(user_obj, udid).count()


def resign_by_app_id_and_developer(app_id, developer_id, developer_app_id, need_download_profile=True, force=True):
    """
    :param app_id:
    :param developer_id:
    :param developer_app_id:
    :param need_download_profile:
    :param force:  检测到已经是最新签名了，是否还继续强制签名， True 表示 强制， False 表示不强制，默认强制继续签名
    :return:
    """
    app_obj = Apps.objects.filter(pk=app_id).first()
    developer_obj = AppIOSDeveloperInfo.objects.filter(pk=developer_id).first()
    if check_ipa_is_latest_sign(app_obj, developer_obj) and not force:
        return
    add_new_bundles_prefix = f"check_or_add_new_bundles_{developer_obj.issuer_id}_{app_obj.app_id}"
    if CleanErrorBundleIdSignDataState(add_new_bundles_prefix).get_state():
        return False, '清理执行中，请等待'
    d_time = time.time()
    if need_download_profile:
        if developer_obj.status not in Config.DEVELOPER_RESIGN_STATUS:
            return False, f'开发者状态 {developer_obj.get_status_display()}，无法下载描述文件'
        with cache.lock(f"make_and_download_profile_{developer_obj.issuer_id}_{app_obj.app_id}", timeout=60):
            IosUtils.modify_capability(developer_obj, app_obj, developer_app_id)
            status, download_profile_result = IosUtils.make_and_download_profile(app_obj,
                                                                                 developer_obj,
                                                                                 add_new_bundles_prefix)
    else:
        status = True
    if status:
        locker = {
            'locker_key': f"run_sign_{app_obj.app_id}_{developer_obj.issuer_id}",
            "timeout": 60 * 5}
        status, result = IosUtils.run_sign(app_obj.user_id, app_obj, developer_obj, d_time, locker=locker)
        return status, {'developer_id': developer_obj.issuer_id, 'result': (status, result)}


def check_app_sign_limit(app_obj):
    used_num = APPSuperSignUsedInfo.objects.filter(app_id=app_obj).all().count()
    limit_num = app_obj.supersign_limit_number
    if limit_num <= 0:
        flag = True
    else:
        flag = used_num < limit_num
    return flag, used_num


def udid_bytes_to_dict(xml_stream):
    new_uuid_info = {}
    try:
        a = xml_stream.find('<plist')
        b = xml_stream.find('</plist>')
        xml_dict = xmltodict.parse(xml_stream[a:b + 8])  # 解析xml字符串
        for i in range(len(xml_dict['plist']['dict']['key'])):
            new_uuid_info[xml_dict['plist']['dict']['key'][i].lower()] = xml_dict['plist']['dict']['string'][i]
    except Exception as e:
        logger.error(f"udid_xml_stream:{xml_stream} Exception:{e}")
        return None
    return new_uuid_info


def make_sign_udid_mobile_config(udid_url, bundle_id, app_name):
    if Config.MOBILE_CONFIG_SIGN_SSL.get("open"):
        ssl_key_path = Config.MOBILE_CONFIG_SIGN_SSL.get("ssl_key_path", None)
        ssl_pem_path = Config.MOBILE_CONFIG_SIGN_SSL.get("ssl_pem_path", None)
        ssl_key_cache = RedisCacheBase(AesBaseCrypt().get_encrypt_uid(ssl_key_path))
        ssl_pem_cache = RedisCacheBase(AesBaseCrypt().get_encrypt_uid(ssl_pem_path))
        ssl_key_data = ssl_key_cache.get_storage_cache()
        ssl_pem_data = ssl_pem_cache.get_storage_cache()
        if not ssl_key_data or not ssl_pem_data:
            if ssl_key_path and ssl_pem_path and os.path.isfile(ssl_key_path) and os.path.isfile(ssl_pem_path):
                ssl_key_cache.set_storage_cache(open(ssl_key_path, 'rb').read(), 24 * 3600)
                ssl_pem_cache.set_storage_cache(open(ssl_pem_path, 'rb').read(), 24 * 3600)
                ssl_key_data = ssl_key_cache.get_storage_cache()
                ssl_pem_data = ssl_pem_cache.get_storage_cache()

        if ssl_key_data and ssl_pem_data:
            status, result = ResignApp.sign_mobile_config(make_udid_mobile_config(udid_url, bundle_id, app_name),
                                                          ssl_pem_path, ssl_key_path, ssl_pem_data, ssl_key_data)
            if status and result.get('data'):
                buffer = BytesIO(result.get("data"))  # uwsgi 无法解析该类型，需求加上 FileWrapper 包装
                return FileWrapper(buffer)
            else:
                logger.error(
                    f"{bundle_id} {app_name} sign_mobile_config failed ERROR:{result.get('err_info')}")
                return make_udid_mobile_config(udid_url, bundle_id, app_name)

        else:
            logger.error(f"sign_mobile_config {ssl_key_path} or {ssl_pem_path} is not exists")
            return make_udid_mobile_config(udid_url, bundle_id, app_name)

    else:
        return make_udid_mobile_config(udid_url, bundle_id, app_name)


def make_udid_mobile_config(udid_url, payload_organization, app_name, payload_uuid=uuid.uuid1(),
                            payload_description='该文件仅用来获取设备ID，帮助用户安装授权',
                            display_name='设备安装授权'):
    # <!--参考:https://developer.apple.com/library/ios/documentation/NetworkingInternet/Conceptual/iPhoneOTAConfiguration/ConfigurationProfileExamples/ConfigurationProfileExamples.html-->
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
    <dict>
        <key>PayloadContent</key>
        <dict>
            <key>URL</key>
            <string>{udid_url}</string>
            <key>DeviceAttributes</key>
            <array>
                <string>SERIAL</string>
                <string>UDID</string>
                <string>IMEI</string>
                <string>ICCID</string>
                <string>VERSION</string>
                <string>PRODUCT</string>
            </array>
        </dict>
        <key>PayloadOrganization</key>
        <string>{payload_organization}</string>
        <key>PayloadDisplayName</key>
        <string>{app_name}--{display_name}</string>
        <key>PayloadVersion</key>
        <integer>1</integer>
        <key>PayloadUUID</key>
        <string>{payload_uuid}</string>
        <key>PayloadIdentifier</key>
        <string>{payload_organization}.profile-service</string>
        <key>PayloadDescription</key>
        <string>{payload_description}</string>
        <key>PayloadType</key>
        <string>Profile Service</string>
    </dict>
</plist>'''


def get_auth_form_developer(developer_obj):
    if developer_obj.issuer_id:
        auth = {
            "issuer_id": developer_obj.issuer_id,
            "private_key_id": developer_obj.private_key_id,
            "p8key": developer_obj.p8key,
            "cert_id": developer_obj.certid
        }
    else:
        auth = {}
    return auth


def get_api_obj(developer_obj, app_obj=None):
    auth = get_auth_form_developer(developer_obj)
    if auth.get("issuer_id"):
        app_api_obj = AppDeveloperApiV2(**auth, developer_pk=developer_obj.pk, app_obj=app_obj)
    else:
        app_api_obj = None
    return app_api_obj


def get_apple_udid_key(auth):
    m_key = ''
    if auth.get("issuer_id"):
        m_key = auth.get("issuer_id")
    return m_key


def get_new_developer_by_app_obj(app_obj, obj_base_filter, apple_to_app=False):
    can_used_developer_pk_list = []
    if apple_to_app:
        # 存在指定开发者，则新设备优先注册到指定开发者
        developer_obj_lists = obj_base_filter.filter(appledevelopertoappuse__app_id=app_obj)
    else:
        developer_obj_lists = obj_base_filter.exclude(appledevelopertoappuse__developerid__isnull=False)
    developer_obj_lists = developer_obj_lists.all().distinct().order_by("created_time")
    for developer_obj in developer_obj_lists:
        # 通过开发者数限制进行过滤
        if get_developer_udided(developer_obj)[2] < developer_obj.usable_number:
            if apple_to_app:
                apple_to_app_obj = AppleDeveloperToAppUse.objects.filter(app_id=app_obj,
                                                                         developerid=developer_obj).first()
                if apple_to_app_obj:
                    # 通过配置的专属分配数量进行过滤
                    app_used_number = DeveloperDevicesID.objects.filter(developerid=developer_obj)
                    if app_used_number.filter(app_id=app_obj).distinct().count() < apple_to_app_obj.usable_number:
                        can_used_developer_pk_list.append(developer_obj.pk)
            else:
                app_used_count = DeveloperAppID.objects.filter(developerid=developer_obj).distinct().count()
                if app_used_count < developer_obj.app_limit_number:
                    can_used_developer_pk_list.append(developer_obj.pk)
    return can_used_developer_pk_list


def filter_developer_by_pk_list(developer_pk_list, f_key, app_search_flag=True):
    developer_obj_dict = AppIOSDeveloperInfo.objects.filter(pk__in=developer_pk_list).values(
        f_key, 'pk').annotate(count=Count('pk'))
    if app_search_flag:
        return developer_obj_dict
    else:
        apple_filter = {f'{f_key}__isnull': False, 'pk__in': developer_pk_list}
        developer_obj_dict = AppIOSDeveloperInfo.objects.filter(**apple_filter).values(f_key, 'pk').annotate(
            count=Count('pk')).filter(count__lt=F('app_limit_number'))
        if not developer_obj_dict:
            apple_filter = {f'{f_key}__isnull': True, 'pk__in': developer_pk_list}
            developer_obj_dict = AppIOSDeveloperInfo.objects.filter(**apple_filter).values(f_key, 'pk').annotate(
                count=Count('pk'))

    return developer_obj_dict


def get_developer_by_pk_list(developer_pk_list, f_key, app_search_flag=True):
    developer_obj_dict = filter_developer_by_pk_list(developer_pk_list, f_key, app_search_flag)
    developer_obj_dict = developer_obj_dict.order_by('created_time').order_by('count').first()
    if developer_obj_dict:
        developer_obj = AppIOSDeveloperInfo.objects.filter(pk=developer_obj_dict.get('pk')).first()
        logger.info(f'get {f_key} suitable developer {developer_obj} and return')
        return developer_obj


def get_developer_user_by_app_exist_udid(user_objs, udid, app_obj, abnormal_use_status):
    status_filter = {'developerid__certid__isnull': False, 'developerid__status__in': abnormal_use_status,
                     'status__in': [DeviceStatus.ENABLED, DeviceStatus.DISABLED]}

    developer_udid_queryset = UDIDsyncDeveloper.objects.filter(developerid__user_id__in=user_objs,
                                                               **status_filter).values('developerid').all().distinct()

    # 根据udid和应用查找该用户开发者账户【主要可能是开发者未激活】
    developer_pk_list = developer_udid_queryset.filter(udid=udid, developerid__apptodeveloper__app_id=app_obj)
    app_search_flag = True

    # 联合udid和应用查询不到数据，那么，仅根据udid查找开发者账户
    if not developer_pk_list:
        app_search_flag = False
        developer_pk_list = developer_udid_queryset.filter(udid=udid)

    # 若根据udid查找开发者账户，则通过应用签名数量进行过滤开发者账户，对应用已经存在开发者，则无需过滤
    # 即使udid已经存在某个开发者，但是签名数量限制，也会将该udid注册到新的开发者，虽然会浪费设备数，但是也许是为了安全？？？！！！
    # 苹果开发者的 bundleId 具体多大限制是未知的，因此定义了 app_limit_number 字段，最大值为160（该数值是理论估计值，具体可修改）
    if developer_pk_list:
        developer_obj = get_developer_by_pk_list(developer_pk_list, 'developerappid', app_search_flag)
        if developer_obj:
            if app_search_flag:
                logger.info(f'udid:{udid} and app_obj:{app_obj} exist and return. developer_obj: {developer_obj}')
            else:
                logger.info(f'udid:{udid} exist and return. app_obj:{app_obj} developer_obj: {developer_obj}')
            return developer_obj, True
    else:
        logger.info(f"udid:{udid} is a new device. app_obj:{app_obj} will find a suitable developer and register it")

    return developer_udid_queryset, False


def get_developer_user_by_app_new_udid(user_objs, udid, app_obj, status_choice, private_first, abnormal_register=False):
    # 新设备查找策略
    # 根据app查找开发者账户
    exist_app_developer_pk_list = []
    status_filter = {'developerid__certid__isnull': False, 'developerid__status__in': status_choice}
    if abnormal_register:
        status_filter['developerid__abnormal_register'] = abnormal_register
    developer_pk_list = UDIDsyncDeveloper.objects.filter(developerid__user_id__in=user_objs,
                                                         developerid__apptodeveloper__app_id=app_obj,
                                                         **status_filter).values('developerid').all().distinct()
    if developer_pk_list:
        for developer_obj in AppIOSDeveloperInfo.objects.filter(pk__in=developer_pk_list):
            if get_developer_udided(developer_obj)[2] < developer_obj.usable_number:
                exist_app_developer_pk_list.append(developer_obj.pk)

    # 查询状态正常的专属开发者信息，判断是否为专属应用
    apple_to_app = AppleDeveloperToAppUse.objects.filter(app_id=app_obj, **status_filter).first()

    # 存在专属开发者账户，但是也同时存在已经安装的设备，优先选择已经安装设备的开发者账户？是or否
    # 是：使应用趋向于一个开发者，为后期更新提供方便
    # 否：优先使用专属开发者进行签名，默认值为否，则专属优先
    if not private_first and apple_to_app and exist_app_developer_pk_list:
        return AppIOSDeveloperInfo.objects.filter(pk=exist_app_developer_pk_list[0]).first(), False

    status_filter = {'certid__isnull': False, 'status__in': status_choice}
    if abnormal_register:
        status_filter['abnormal_register'] = abnormal_register
    obj_base_filter = AppIOSDeveloperInfo.objects.filter(user_id__in=user_objs, **status_filter)

    can_used_developer_pk_list = get_new_developer_by_app_obj(app_obj, obj_base_filter, apple_to_app)

    # 存在指定开发者账户，但是获取可用的开发者账户为空，那么开始匹配全部开发者
    if not can_used_developer_pk_list and apple_to_app:
        logger.info(f"udid:{udid} app_obj:{app_obj} private developer is null. start find all developer")
        can_used_developer_pk_list = get_new_developer_by_app_obj(app_obj, obj_base_filter)

    if can_used_developer_pk_list and exist_app_developer_pk_list:
        can_used_developer_pk_list = list(set(can_used_developer_pk_list) & set(exist_app_developer_pk_list))
        logger.info(f"udid:{udid} app_obj:{app_obj} find private and can use developer {can_used_developer_pk_list}")

    # 查询开发者策略 按照最小注册设备数进行查找，这样可以分散，进而使应用趋向于一个开发者，为后期更新提供方便
    if can_used_developer_pk_list:
        developer_obj = get_developer_by_pk_list(can_used_developer_pk_list, 'udidsyncdeveloper')
        if developer_obj:
            logger.info(f"udid:{udid} is a new device. app_obj:{app_obj} find {developer_obj} and return")
            return developer_obj, False
    return None, None


def get_developer_user_by_app_udid(user_objs, udid, app_obj, private_first=True, read_only=True):
    """
    :param read_only:
    :param user_objs: [user_obj]
    :param udid: udid
    :param app_obj: app_obj
    :param private_first: 专属应用优先使用专属开发者，而不是公共开发者
    :return:  (developer_obj, is_exist_devices)
    """

    if read_only:
        status_choice = Config.DEVELOPER_USE_STATUS
    else:
        status_choice = Config.DEVELOPER_SIGN_STATUS

    base_msg = f"{'read mode' if read_only else 'write mode'} did:{udid} app_obj:{app_obj}"

    # 已经存在设备查找策略
    obj, status = get_developer_user_by_app_exist_udid(user_objs, udid, app_obj, status_choice)
    if status:
        return obj, status
    else:
        logger.warning(f"{base_msg} find udid from normal developer failed. now find abnormal device developer")

    obj, status = get_developer_user_by_app_exist_udid(user_objs, udid, app_obj, [AppleDeveloperStatus.DEVICE_ABNORMAL])
    if status:
        return obj, status
    else:
        logger.warning(f"{base_msg} find udid from abnormal developer failed. now find can wait developer")

    if UserConfig(app_obj.user_id).DEVELOPER_WAIT_ABNORMAL_STATE:
        obj, status = get_developer_user_by_app_exist_udid(user_objs, udid, app_obj, Config.DEVELOPER_WAIT_STATUS)
        if status:
            return obj, status
        else:
            logger.warning(f"{base_msg} find udid from abnormal developer failed. now find register developer")

    if read_only:
        return None, None

    # 新设备查找策略
    # 查询开发者正常的状态
    obj, status = get_developer_user_by_app_new_udid(user_objs, udid, app_obj, status_choice, private_first)
    if obj:
        return obj, status
    else:
        logger.warning(f"{base_msg} register udid from normal developer failed. now find abnormal device developer")

        # 个人配置允许查询异常设备
    if UserConfig(app_obj.user_id).DEVELOPER_WAIT_ABNORMAL_DEVICE and UserConfig(
            app_obj.user_id).DEVELOPER_ABNORMAL_DEVICE_WRITE:
        status_choice = [AppleDeveloperStatus.DEVICE_ABNORMAL]
        obj, status = get_developer_user_by_app_new_udid(user_objs, udid, app_obj, status_choice, private_first, True)
    return obj, status


def get_developer_obj_by_others(user_obj, udid, app_obj, read_only):
    result, is_exist = get_developer_user_by_app_udid([user_obj], udid, app_obj, read_only=read_only)
    if result:
        return result
    receive_user_id_list = IosDeveloperBill.objects.filter(to_user_id=user_obj, status=2).values('user_id').distinct()
    if receive_user_id_list:
        result, is_exist = get_developer_user_by_app_udid(UserInfo.objects.filter(pk__in=receive_user_id_list), udid,
                                                          app_obj, read_only=read_only)
    f_count = get_ios_developer_public_num(user_obj)

    if (f_count == 0 and is_exist) or f_count > 0:
        return result


def check_sign_is_exists(user_obj, app_obj, udid, developer_obj, sign=True):
    d_result = {'code': 1000, 'msg': 'success'}
    app_udid_obj = AppUDID.objects.filter(app_id=app_obj, udid__udid=udid, udid__developerid=developer_obj).first()
    if app_udid_obj and app_udid_obj.sign_status >= SignStatus.PROFILE_DOWNLOAD_COMPLETE:
        if app_udid_obj.sign_status == SignStatus.SIGNATURE_PACKAGE_COMPLETE:
            if check_ipa_is_latest_sign(app_obj, developer_obj, app_udid_obj):
                d_result['msg'] = f'udid {udid} exists app_id {app_obj}'
                logger.warning(d_result)
                return True, d_result
            else:
                sign_flag = True
        else:
            sign_flag = True
        if sign_flag and sign:
            locker = {
                'locker_key': f"run_sign_{app_obj.app_id}_{developer_obj.issuer_id}",
                "timeout": 60 * 5
            }
            logger.warning(f"udid {udid} is exist but app_id {app_obj} not sign. start run_sign ...")
            return IosUtils.run_sign(user_obj, app_obj, developer_obj, time.time(), [udid], locker=locker)
    logger.warning(f"udid {udid} not exist app_id {app_obj} . start find developer and sign")


def change_developer_abnormal_status(developer_status, user_obj, developer_obj, app_obj):
    if developer_status == AppleDeveloperStatus.ACTIVATED and developer_obj.status != developer_status:
        sign_failed_notify(user_obj, developer_obj, app_obj)


class IosUtils(object):
    def __init__(self, udid_info, user_obj, app_obj=None):
        self.developer_obj = None
        self.auth = None
        self.udid_info = udid_info
        self.udid = udid_info.get('udid')
        self.app_obj = app_obj
        self.user_obj = user_obj

    def get_developer_auth(self, read_only=True):
        self.developer_obj = get_developer_obj_by_others(self.user_obj, self.udid, self.app_obj, read_only)
        if self.developer_obj:
            self.auth = get_auth_form_developer(self.developer_obj)
        else:
            if read_only:
                return
            logger.error(f"user {self.user_obj} has no active apple developer")
            if send_msg_over_limit("get", self.user_obj.email):
                send_msg_over_limit("set", self.user_obj.email)
                sign_unavailable_developer_notify(self.user_obj, self.app_obj)
            else:
                logger.error(f"user {self.user_obj} send msg failed. over limit")

    # def download_profile(self, developer_app_id, device_id_list):
    #     return get_api_obj(self.auth).get_profile(self.app_obj, self.udid_info,
    #                                               self.get_profile_full_path(),
    #                                               self.auth, developer_app_id, device_id_list, )

    # 开启超级签直接在开发者账户创建
    # def create_app(self, app_obj):
    #     bundleId = self.app_obj.bundle_id
    #     app_id = self.app_obj.app_id
    #     s_type = self.app_obj.supersign_type
    #     return get_api_obj(self.auth).create_app(bundleId, app_id, s_type)

    @staticmethod
    def modify_capability(developer_obj, app_obj, developer_app_id):
        return get_api_obj(developer_obj, app_obj).modify_capability(app_obj, developer_app_id)

    def get_profile_full_path(self):
        cert_dir_name = make_app_uuid(self.user_obj, get_apple_udid_key(self.auth))
        cert_dir_path = os.path.join(SUPER_SIGN_ROOT, cert_dir_name, "profile")
        if not os.path.isdir(cert_dir_path):
            os.makedirs(cert_dir_path)
        provision_name = os.path.join(cert_dir_path, self.app_obj.app_id)
        return provision_name + '.mobileprovision'

    @staticmethod
    def zip_cert(user_obj, developer_obj):
        auth = get_auth_form_developer(developer_obj)
        file_format_path_name = file_format_path(user_obj, auth)
        os.chdir(os.path.dirname(file_format_path_name))
        zip_file_path = file_format_path_name + '.zip'
        zipf = zipfile.ZipFile(zip_file_path, mode='w', compression=zipfile.ZIP_DEFLATED)
        for file in os.listdir(os.path.dirname(file_format_path_name)):
            if os.path.isfile(file) and file.startswith(os.path.basename(file_format_path_name)) and \
                    file.split('.')[-1] not in ['zip', 'bak']:
                zipf.write(file)
        zipf.close()
        return zip_file_path

    @staticmethod
    def get_resign_obj(user_obj, developer_obj):
        auth = get_auth_form_developer(developer_obj)
        file_format_path_name = file_format_path(user_obj, auth)
        my_local_key = file_format_path_name + ".key"
        app_dev_pem = file_format_path_name + ".pem"
        app_dev_p12 = file_format_path_name + ".p12"
        return ResignApp(my_local_key, app_dev_pem, app_dev_p12)

    @staticmethod
    def exec_sign(user_obj, app_obj, developer_obj, random_file_name, release_obj):
        resign_app_obj = IosUtils.get_resign_obj(user_obj, developer_obj)
        org_file = os.path.join(MEDIA_ROOT, release_obj.release_id + ".ipa")
        if not check_org_file(user_obj, org_file):
            msg = f"{user_obj} {developer_obj} {app_obj} sign_ipa failed ERROR:'签名包检测失败，或许文件下载失败'"
            logger.error(msg)
            return False, msg
        new_file = os.path.join(MEDIA_ROOT, random_file_name + ".ipa")
        properties_info = {}
        if app_obj.new_bundle_id:
            properties_info.update({'-b': app_obj.new_bundle_id})
        if app_obj.new_bundle_name:
            properties_info.update({'-n': app_obj.new_bundle_name})
        status, result = resign_app_obj.sign(get_profile_full_path(developer_obj, app_obj), org_file, new_file,
                                             properties_info)
        if status:
            logger.info(f"{user_obj} {developer_obj} {app_obj} sign_ipa success")
            return True, result
        else:
            logger.error(f"{user_obj} {developer_obj} {app_obj} sign_ipa failed ERROR:{result.get('err_info')}")
            return False, result

    @staticmethod
    def update_sign_file_name(user_obj, app_obj, developer_obj_id, release_obj, random_file_name):
        apptodev_obj = APPToDeveloper.objects.filter(developerid_id=developer_obj_id, app_id=app_obj).first()
        storage_obj = get_sign_oss_storage(user_obj)
        logger.info(f"update sign file end, now upload {storage_obj.storage} {random_file_name}.ipa file")
        with cache.lock(f"upload_files_form_oss_{random_file_name}", timeout=60 * 30):
            if storage_obj.upload_file(os.path.join(MEDIA_ROOT, random_file_name + ".ipa")):
                if apptodev_obj:
                    delete_local_files(apptodev_obj.binary_file + ".ipa")
                    storage_obj.delete_file(apptodev_obj.binary_file + ".ipa")
                    apptodev_obj.binary_file = random_file_name
                    old_release_file = apptodev_obj.release_file
                    apptodev_obj.release_file = release_obj.release_id
                    apptodev_obj.save(update_fields=['binary_file', 'release_file', 'updated_time'])
                    if storage_obj.get_storage_type() in [1, 2] and old_release_file != release_obj.release_id:
                        logger.warning(f"update sign file , now clean ole {old_release_file}.ipa file")
                        delete_local_files(old_release_file + ".ipa")
                else:
                    APPToDeveloper.objects.create(developerid_id=developer_obj_id, app_id=app_obj,
                                                  binary_file=random_file_name, release_file=release_obj.release_id)
                if storage_obj.get_storage_type() in [1, 2]:
                    delete_local_files(random_file_name + ".ipa")
                return True

    @staticmethod
    def update_sign_data(user_obj, app_obj, developer_obj_id, random_file_name, release_obj, udid_list):
        # 更新新签名的ipa包
        if IosUtils.update_sign_file_name(user_obj, app_obj, developer_obj_id, release_obj,
                                          random_file_name):
            if udid_list:
                for udid in udid_list:
                    udid_obj = UDIDsyncDeveloper.objects.filter(developerid_id=developer_obj_id, udid=udid).first()
                    AppUDID.objects.filter(app_id=app_obj,
                                           udid=udid_obj,
                                           sign_status=SignStatus.PROFILE_DOWNLOAD_COMPLETE).update(
                        sign_status=SignStatus.SIGNATURE_PACKAGE_COMPLETE)
                    base_app_udid = AppUDID.objects.filter(app_id=app_obj, udid__developerid_id=developer_obj_id)
                    if base_app_udid.filter(sign_status__lt=SignStatus.SIGNATURE_PACKAGE_COMPLETE).count():
                        c_time = base_app_udid.filter(sign_status__lt=SignStatus.SIGNATURE_PACKAGE_COMPLETE).order_by(
                            '-created_time').first()
                        u_time = base_app_udid.filter(sign_status=SignStatus.SIGNATURE_PACKAGE_COMPLETE).order_by(
                            '-updated_time').first()
                        if c_time and u_time and u_time.updated_time > c_time.created_time:
                            base_app_udid.update(sign_status=SignStatus.SIGNATURE_PACKAGE_COMPLETE)

            del_cache_response_by_short(app_obj.app_id)
            MagicCacheData.invalid_cache(app_obj.app_id)
            return True

    def check_sign_permission(self):
        d_result = {'code': 1000, 'msg': 'success'}
        state, used_num = check_app_sign_limit(self.app_obj)
        if not state:
            d_result['code'] = 1003
            d_result[
                'msg'] = f"app_id {self.app_obj} used over limit.now {used_num} limit: {self.app_obj.supersign_limit_number}"
            logger.error(d_result)
            add_sign_message(self.user_obj, self.developer_obj, self.app_obj, '签名余额不足', d_result['msg'], False)
            sign_app_over_limit_notify(self.app_obj.user_id, self.app_obj, used_num,
                                       self.app_obj.supersign_limit_number)
            return False, d_result

        res = check_app_permission(self.app_obj, BaseResponse())
        if res.code != 1000:
            return False, {'code': res.code, 'msg': res.msg}
        return True, d_result

    @staticmethod
    @call_function_try_attempts()
    def check_or_register_devices(app_obj, user_obj, developer_obj, udid_info, client_ip, failed_call_prefix):
        """
        :param user_obj:
        :param client_ip:
        :param failed_call_prefix:
        :param app_obj:
        :param developer_obj:
        :param udid_info:
        :return:
        """
        device_udid = udid_info.get('udid')
        device_name = udid_info.get('product')
        developer_status = developer_obj.status
        if not device_udid:
            logger.error("device udid is not exists. so return and exit")
            return True, 'continue'

        register_failed_callback = [
            {
                'func_list': [magic_wrapper(IosUtils.get_device_from_developer, developer_obj)],
                'err_match_msg': [
                    "There are no current ios devices",
                    "Your development team has reached the maximum number of registered iPhone devices"
                ]
            }
        ]
        set_failed_callback = [
            {
                'func_list': [magic_wrapper(IosUtils.get_device_from_developer, developer_obj)],
                'err_match_msg': [
                    "There are no current ios devices",
                    "Device obj is None"
                ]
            },
            {
                'func_list': [magic_wrapper(IosUtils.check_device_status, developer_obj)],
                'err_match_msg': [
                    "ENTITY_ERROR.ATTRIBUTE.INVALID.DUPLICATE",
                ]
            },
        ]

        sync_device_obj = UDIDsyncDeveloper.objects.filter(udid=device_udid,
                                                           developerid=developer_obj).first()
        # auth = get_auth_form_developer(developer_obj)
        # 库里面存在，并且设备是可用状态，因此无需api注册
        if sync_device_obj:
            logger.info(f"app {app_obj} device {sync_device_obj.serial} already in developer {developer_obj}")
            if sync_device_obj.status != DeviceStatus.ENABLED:
                # 库里面存在，并且设备是禁用状态，需要调用api启用
                status, result = get_api_obj(developer_obj, app_obj).set_device_status("enable", sync_device_obj.serial,
                                                                                       sync_device_obj.product,
                                                                                       sync_device_obj.udid,
                                                                                       failed_call_prefix,
                                                                                       set_failed_callback)
                if not status:  # 已经包含异常操作，暂定
                    msg = result
                    sync_device_obj = UDIDsyncDeveloper.objects.filter(udid=device_udid,
                                                                       developerid=developer_obj,
                                                                       status__in=[DeviceStatus.PROCESSING,
                                                                                   DeviceStatus.INELIGIBLE]).first()
                    if sync_device_obj:
                        change_developer_abnormal_status(developer_status, user_obj, developer_obj, app_obj)
                        if UserConfig(user_obj).DEVELOPER_WAIT_ABNORMAL_DEVICE:
                            update_or_create_abnormal_device(sync_device_obj, user_obj, app_obj, client_ip)
                            msg = 'DEVELOPER_WAIT_ABNORMAL_DEVICE'
                    return False, msg
                sync_device_obj.status = result.statue
                sync_device_obj.save(update_fields=['status'])

        else:
            # 库里面不存在，注册设备，新设备注册默认就是启用状态
            status, device_obj = get_api_obj(developer_obj, app_obj).register_device(device_udid, device_name,
                                                                                     failed_call_prefix,
                                                                                     register_failed_callback)
            if not status:
                return status, device_obj

            if device_obj and device_obj.status not in [DeviceStatus.ENABLED, DeviceStatus.DISABLED]:
                status, sync_device_obj = IosUtils.check_device_status(developer_obj, serial=device_obj.id)
                if not status:
                    sync_device_obj, _ = update_or_create_developer_udid_info(device_obj, developer_obj)
                    msg = '设备状态异常'
                    change_developer_abnormal_status(developer_status, user_obj, developer_obj, app_obj)
                    if UserConfig(user_obj).DEVELOPER_WAIT_ABNORMAL_DEVICE:
                        update_or_create_abnormal_device(sync_device_obj, user_obj, app_obj, client_ip)
                        msg = 'DEVELOPER_WAIT_ABNORMAL_DEVICE'
                    return False, msg
            else:
                sync_device_obj, _ = update_or_create_developer_udid_info(device_obj, developer_obj)

        # 更新设备状态
        # 1. UDIDsyncDeveloper 库，通过udid 更新或创建设备信息
        # 2. DeveloperDevicesID 添加新应用-设备绑定信息数据
        # 3. AppUDID 添加数据，该数据主要是为了记录使用，is_signed 判断是否已经签名成功
        del udid_info['udid']
        udid_info['sign_status'] = SignStatus.DEVICE_REGISTRATION_COMPLETE
        # udid_info['is_download'] = False
        udid_obj, _ = AppUDID.objects.update_or_create(app_id=app_obj, udid=sync_device_obj,
                                                       defaults=udid_info)

        DeveloperDevicesID.objects.update_or_create(did=sync_device_obj.serial, udid=sync_device_obj,
                                                    developerid=developer_obj,
                                                    app_id=app_obj)

        APPSuperSignUsedInfo.objects.update_or_create(app_id=app_obj,
                                                      user_id=user_obj,
                                                      developerid=developer_obj,
                                                      udid=udid_obj)
        udid_sync_info = UDIDsyncDeveloper.objects.filter(developerid=developer_obj,
                                                          udid=device_udid).first()
        IosDeveloperPublicPoolBill.objects.update_or_create(user_id=user_obj,
                                                            app_info=BillAppInfoSerializer(app_obj).data,
                                                            developer_info=BillDeveloperInfoSerializer(
                                                                developer_obj).data,
                                                            number=1, udid_sync_info=udid_sync_info,
                                                            remote_addr=client_ip, product=udid_sync_info.product,
                                                            udid=device_udid, version=udid_sync_info.version,
                                                            app_id=app_obj
                                                            )

        return True, (sync_device_obj.serial, sync_device_obj.udid)

    @staticmethod
    @call_function_try_attempts()
    def check_or_add_new_bundles(app_obj, developer_obj, add_new_bundles_prefix, failed_callback=None):
        if failed_callback is None:
            failed_callback = []
        failed_callback.extend([
            {
                'func_list': [magic_wrapper(IosUtils.clean_super_sign_things_by_app_obj, app_obj, developer_obj)],
                'err_match_msg': ["There is no App ID with ID"]
            }
        ])
        developer_app_id_obj = DeveloperAppID.objects.filter(developerid=developer_obj,
                                                             app_id=app_obj).first()
        if not developer_app_id_obj:
            bundle_id = app_obj.bundle_id
            app_id = app_obj.app_id
            s_type = app_obj.supersign_type
            status, result = get_api_obj(developer_obj, app_obj).create_app(bundle_id, app_id, s_type,
                                                                            add_new_bundles_prefix,
                                                                            failed_callback)
            if status and result.get('aid'):
                developer_app_id_obj = DeveloperAppID.objects.create(aid=result.get('aid'), developerid=developer_obj,
                                                                     app_id=app_obj)
            else:
                return status, result
        AppUDID.objects.filter(app_id=app_obj,
                               udid__developerid_id=developer_obj,
                               sign_status=SignStatus.DEVICE_REGISTRATION_COMPLETE).update(
            sign_status=SignStatus.APP_REGISTRATION_COMPLETE)
        return True, developer_app_id_obj

    @staticmethod
    @call_function_try_attempts(try_attempts=2)
    def check_device_status(developer_obj, device_obj_list=None, serial=None):
        status = True
        if device_obj_list is None:
            status, device_obj_list = get_api_obj(developer_obj).get_device()
        if status:
            for device_obj in device_obj_list:
                if device_obj.status not in [DeviceStatus.ENABLED, DeviceStatus.DISABLED]:
                    err_msg = f'issuer_id:{developer_obj.issuer_id} device status unexpected. device_obj:{device_obj}'
                    if developer_obj.status != AppleDeveloperStatus.DEVICE_ABNORMAL:
                        developer_obj.status = AppleDeveloperStatus.DEVICE_ABNORMAL
                        developer_obj.save(update_fields=['status'])
                        add_sign_message(developer_obj.user_id, developer_obj, None, '开发者设备状态异常',
                                         err_msg, False)
                    if serial:
                        if serial == device_obj.id:
                            return False, err_msg
                    else:
                        return False, err_msg
                else:
                    if serial and serial == device_obj.id:
                        sync_device_obj, _ = update_or_create_developer_udid_info(device_obj, developer_obj)
                        return True, sync_device_obj
        return True, ''

    @staticmethod
    @call_function_try_attempts(try_attempts=2)
    def make_and_download_profile(app_obj, developer_obj, failed_call_prefix, developer_app_id_obj=None,
                                  new_did_list=None,
                                  failed_callback=None):
        if new_did_list is None:
            new_did_list = []

        if failed_callback is None:
            failed_callback = []

        failed_callback.extend([
            {
                'func_list': [magic_wrapper(IosUtils.active_developer, developer_obj, False)],
                'err_match_msg': [
                    "There are no current certificates on this team matching the provided certificate",
                    "MUST contain type and id members"
                ]
            },
            {
                'func_list': [magic_wrapper(IosUtils.check_device_status, developer_obj)],
                'err_match_msg': ["There are no current ios devices on this team matching the provided device IDs"]
            },
            {
                'func_list': [magic_wrapper(IosUtils.clean_super_sign_things_by_app_obj, app_obj, developer_obj)],
                'err_match_msg': [
                    "There is no App ID with ID",
                    "There are no current certificates on this team matching the provided certificate"
                ]
            }
        ])
        device_id_list = DeveloperDevicesID.objects.filter(app_id=app_obj,
                                                           developerid=developer_obj).values_list('did')
        device_id_lists = [did[0] for did in device_id_list]
        if new_did_list:
            device_id_lists.extend(new_did_list)
            device_id_lists = list(set(device_id_lists))
        if not developer_app_id_obj:
            developer_app_id_obj = DeveloperAppID.objects.filter(developerid=developer_obj, app_id=app_obj).first()
            if not developer_app_id_obj:
                logger.error(f"app {app_obj} developer {developer_obj} .bundle id not found. so return and exit")
                return True, 'continue'
        developer_app_id = developer_app_id_obj.aid
        profile_id = developer_app_id_obj.profile_id
        auth = get_auth_form_developer(developer_obj)
        status, result = get_api_obj(developer_obj, app_obj).make_and_download_profile(app_obj,
                                                                                       get_profile_full_path(
                                                                                           developer_obj,
                                                                                           app_obj),
                                                                                       auth, developer_app_id,
                                                                                       device_id_lists, profile_id,
                                                                                       failed_call_prefix,
                                                                                       failed_callback,
                                                                                       )

        if not status:
            return False, result
        if result.get("profile_id", None):
            DeveloperAppID.objects.filter(developerid=developer_obj, app_id=app_obj).update(
                profile_id=result.get("profile_id", None))
        return True, True

    def sign_failed_fun(self, d_result, msg):
        d_result['msg'] = msg
        logger.error(d_result)
        add_sign_message(self.user_obj, self.developer_obj, self.app_obj, '签名失败', msg, False)
        logger.error(f"app {self.app_obj} developer {self.developer_obj} sign failed. so disabled")
        if self.developer_obj.status == AppleDeveloperStatus.ACTIVATED:
            self.developer_obj.status = AppleDeveloperStatus.ABNORMAL_STATUS
            self.developer_obj.save(update_fields=['status'])
        sign_failed_notify(self.developer_obj.user_id, self.developer_obj, self.app_obj)

        self.get_developer_auth(False)

    def sign_ipa(self, client_ip):
        status, msg = self.check_sign_permission()
        if not status:
            return status, msg
        d_result = {'code': 1000, 'msg': 'success'}

        self.get_developer_auth(True)
        if self.developer_obj:
            result = check_sign_is_exists(self.user_obj, self.app_obj, self.udid, self.developer_obj)
            if result:
                return result

        if check_udid_black(self.user_obj, self.udid):
            msg = {'code': 1007}
            return False, msg

        self.get_developer_auth(False)

        if self.developer_obj:
            if UserConfig(
                    self.user_obj).DEVELOPER_WAIT_ABNORMAL_STATE and self.developer_obj.status in Config.DEVELOPER_WAIT_STATUS:
                msg = {'code': 1007}
                return False, msg

        logger.info(f"udid {self.udid} not exists app_id {self.app_obj}")

        if consume_user_download_times_by_app_obj(self.app_obj):
            d_result['code'] = 1009
            d_result['msg'] = '可用下载额度不足，请联系开发者'
            logger.error(d_result)
            return False, d_result

        call_flag = True
        count = 0
        start_time = time.time()
        while call_flag:
            count += 1
            if count > 3:
                break
            logger.warning(
                f"call_loop download_profile appid:{self.app_obj} developer:{self.developer_obj} count:{count}")
            if self.developer_obj:
                # register_devices_prefix = f"check_or_register_devices_{self.developer_obj.issuer_id}_{self.udid}"
                issuer_id = self.developer_obj.issuer_id
                register_devices_prefix = f"check_or_register_devices_{issuer_id}"
                add_new_bundles_prefix = f"check_or_add_new_bundles_{issuer_id}_{self.app_obj.app_id}"
                download_profile_prefix = f"make_and_download_profile_{issuer_id}_{self.app_obj.app_id}"

                with cache.lock(register_devices_prefix, timeout=360):
                    if CleanErrorBundleIdSignDataState(add_new_bundles_prefix).get_state():
                        return True, True  # 程序错误，进行清理的时候，拦截多余的设备注册
                    if not get_developer_obj_by_others(self.user_obj, self.udid, self.app_obj, False):
                        d_result['code'] = 1005
                        return False, d_result
                    status, did_udid_result = IosUtils.check_or_register_devices(self.app_obj, self.user_obj,
                                                                                 self.developer_obj,
                                                                                 self.udid_info, client_ip,
                                                                                 add_new_bundles_prefix)
                    if not status:
                        if 'UNEXPECTED_ERROR' in str(did_udid_result):
                            return False, {'code': 1002, 'msg': did_udid_result}
                        if 'DEVELOPER_WAIT_ABNORMAL_DEVICE' in str(did_udid_result):
                            return False, {'code': 1007, 'msg': '设备注册中，请耐心等待'}
                        msg = f"app_id {self.app_obj} register devices failed. {did_udid_result}"
                        self.sign_failed_fun(d_result, msg)
                        continue
                    if status and 'continue' in [str(did_udid_result)]:
                        return True, 'device udid is not exists. so return and exit'
                with cache.lock(add_new_bundles_prefix, timeout=360):
                    status, bundle_result = IosUtils.check_or_add_new_bundles(self.app_obj, self.developer_obj,
                                                                              add_new_bundles_prefix)
                    if not status:
                        if 'UNEXPECTED_ERROR' in str(bundle_result):
                            return False, {'code': 1002, 'msg': bundle_result}
                        msg = f"app_id {self.app_obj} create bundles failed. {bundle_result}"
                        self.sign_failed_fun(d_result, msg)
                        continue
                prefix_key = f"{issuer_id}-{self.app_obj.app_id}"
                if 'continue' not in [str(did_udid_result)]:
                    add_udid_cache_queue(prefix_key, did_udid_result)

                time.sleep(5)
                with cache.lock(download_profile_prefix, timeout=60 * 10):
                    did_udid_lists = get_and_clean_udid_cache_queue(prefix_key)
                    new_did_list = []
                    new_udid_list = []
                    for did_udid in did_udid_lists:
                        if not check_sign_is_exists(self.user_obj, self.app_obj, did_udid[1], self.developer_obj):
                            new_did_list.append(did_udid[0])
                            new_udid_list.append(did_udid[1])
                    if not new_did_list:
                        return True, f'udid {self.udid} not in new_did_list. {self.app_obj}'
                    logger.warning(
                        f'app {self.app_obj} receive {len(new_did_list)} did_udid_result: {new_did_list}')
                    status, download_profile_result = IosUtils.make_and_download_profile(self.app_obj,
                                                                                         self.developer_obj,
                                                                                         add_new_bundles_prefix,
                                                                                         new_did_list=new_did_list)
                    if not status:
                        if 'UNEXPECTED_ERROR' in str(download_profile_result):
                            return False, {'code': 1002, 'msg': download_profile_result}
                        msg = f"app_id {self.app_obj} download profile failed. {download_profile_result}"
                        self.sign_failed_fun(d_result, msg)
                        continue
                    else:
                        if 'continue' in [str(did_udid_result), str(download_profile_result)]:
                            # 该情况估计是执行了回滚清理应用操作，导致异常，大概率是开发证书丢失或苹果开发平台数据被误删
                            return True, f'{self.app_obj} developer {self.developer_obj} may be rollback'
                        locker = {
                            'locker_key': f"run_sign_{self.app_obj.app_id}_{self.developer_obj.issuer_id}",
                            "timeout": 60 * 5
                        }
                        return IosUtils.run_sign(self.user_obj, self.app_obj, self.developer_obj,
                                                 start_time, new_udid_list, locker=locker)

        if not self.developer_obj:
            d_result['code'] = 1005
            d_result['msg'] = '未找到可用苹果开发者'
            logger.error(d_result)
            return False, d_result
        return True, True

    @staticmethod
    @run_function_by_locker()
    def run_sign(user_obj, app_obj, developer_obj, d_time, udid_list=None):
        if udid_list is None:
            udid_list = []
            # app_udid_queryset = AppUDID.objects.filter(app_id=app_obj, udid__developerid=developer_obj).all()
            for udid_obj in UDIDsyncDeveloper.objects.filter(appudid__app_id=app_obj, developerid=developer_obj).all():
                udid_list.append(udid_obj.udid)
        else:
            new_did_list = []
            for did_udid in udid_list:
                if not check_sign_is_exists(user_obj, app_obj, did_udid, developer_obj, False):
                    new_did_list.append(did_udid)
            if not new_did_list:
                return True, f"{app_obj} not udid .so return, maybe it was deleted"
            else:
                udid_list = new_did_list
        udid_list = list(set(udid_list))
        d_result = {'code': 1000, 'msg': 'success'}
        AppUDID.objects.filter(app_id=app_obj, udid__udid__in=udid_list,
                               udid__developerid=developer_obj,
                               sign_status=SignStatus.APP_REGISTRATION_COMPLETE).update(
            sign_status=SignStatus.PROFILE_DOWNLOAD_COMPLETE)
        start_time = time.time()
        logger.info(f"app_id {app_obj} download profile success. time:{start_time - d_time}")
        random_file_name = make_from_user_uuid(developer_obj.user_id.uid)
        release_obj = AppReleaseInfo.objects.filter(app_id=app_obj, is_master=True).first()
        status, e_result = IosUtils.exec_sign(developer_obj.user_id, app_obj, developer_obj, random_file_name,
                                              release_obj)
        if status:
            s_time1 = time.time()
            logger.info(f"app_id {app_obj} exec sign ipa success. time:{s_time1 - start_time}")
            if not IosUtils.update_sign_data(user_obj, app_obj, developer_obj.pk, random_file_name, release_obj,
                                             udid_list):
                d_result['code'] = 1004
                d_result['msg'] = '数据更新失败，请稍后重试'
                return status, d_result
        else:
            # 导致签名问题：
            # 1.描述文件下载失败,也就是描述文件不存在
            # 2.IPA 包打包编码有误，非utf-8编码打包
            # 3.签名证书有误或者不存在
            d_result['code'] = 1004
            d_result['msg'] = '签名失败，请检查包是否正常'
            return status, d_result

        msg = f"app_id {app_obj} developer {developer_obj} sign end... time:{time.time() - start_time}"
        logger.warning(msg)
        d_result['msg'] = msg
        return True, d_result

    @staticmethod
    def disable_udid(udid_obj, app_id, disabled=False):

        usedeviceobj = APPSuperSignUsedInfo.objects.filter(udid=udid_obj, app_id_id=app_id)
        if usedeviceobj:
            developer_obj = usedeviceobj.first().developerid
            # 需要判断该设备在同一个账户下 的多个应用，若存在，则不操作
            udid_lists = list(
                APPSuperSignUsedInfo.objects.values_list("udid__udid__udid").filter(developerid=developer_obj))
            IosUtils.do_disable_device(developer_obj, udid_lists, udid_obj, disabled)
            DeveloperDevicesID.objects.filter(udid__appudid=udid_obj, developerid=developer_obj,
                                              app_id_id=app_id).delete()
            udid_obj.delete()
            # 通过开发者id判断 app_id 是否多个，否则删除profile 文件
            if APPSuperSignUsedInfo.objects.filter(developerid=developer_obj, app_id_id=app_id).count() == 0:
                app_obj = Apps.objects.filter(pk=app_id).first()
                IosUtils.clean_app_by_developer_obj(app_obj, developer_obj)
                delete_app_to_dev_and_file(developer_obj, app_id)
                delete_app_profile_file(developer_obj, app_obj)

    @staticmethod
    def do_disable_device(developer_obj, udid_lists, udid_obj, disabled):
        if udid_lists.count((udid_obj.udid.udid,)) == 1 and disabled:
            app_api_obj = get_api_obj(developer_obj)
            status, result = app_api_obj.set_device_status("disable", udid_obj.udid.serial, udid_obj.udid.product,
                                                           udid_obj.udid.udid, udid_obj.udid.udid)
            if status:
                UDIDsyncDeveloper.objects.filter(udid=udid_obj.udid.udid, developerid=developer_obj).update(
                    status=result.status)
            else:
                logger.error(
                    f'issuer_id: {developer_obj.issuer_id} {developer_obj} {udid_obj.udid.udid} set disabled failed')

    @staticmethod
    def do_enable_device_by_sync(developer_obj, udid_sync_obj):
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.set_device_status("enable", udid_sync_obj.serial, udid_sync_obj.product,
                                                       udid_sync_obj.udid,
                                                       udid_sync_obj.udid)
        if status:
            UDIDsyncDeveloper.objects.filter(pk=udid_sync_obj.pk, developerid=developer_obj).update(
                status=result.status)
        else:
            logger.error(
                f'issuer_id: {developer_obj.issuer_id} {developer_obj} {udid_sync_obj.udid} set enabled failed')

    @staticmethod
    def do_disable_device_by_sync(developer_obj, udid_sync_obj):
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.set_device_status("disable", udid_sync_obj.serial, udid_sync_obj.product,
                                                       udid_sync_obj.udid,
                                                       udid_sync_obj.udid)
        if status:
            UDIDsyncDeveloper.objects.filter(pk=udid_sync_obj.pk, developerid=developer_obj).update(
                status=result.status)
        else:
            logger.error(
                f'issuer_id: {developer_obj.issuer_id} {developer_obj} {udid_sync_obj.udid} set disabled failed')

    @staticmethod
    def clean_udid_by_app_obj(app_obj, developer_obj):

        # 需要判断该设备在同一个账户下 的多个应用，若存在，则不操作
        udid_lists = list(
            APPSuperSignUsedInfo.objects.values_list("udid__udid__udid").filter(developerid=developer_obj))

        for SuperSignUsed_obj in APPSuperSignUsedInfo.objects.filter(app_id=app_obj, developerid=developer_obj):
            try:
                udid_obj = SuperSignUsed_obj.udid
                IosUtils.do_disable_device(developer_obj, udid_lists, udid_obj, developer_obj.clean_status)
                SuperSignUsed_obj.delete()
                DeveloperDevicesID.objects.filter(udid__appudid=udid_obj, developerid=developer_obj,
                                                  app_id=app_obj).delete()
                udid_obj.delete()
            except Exception as e:
                logger.error(f"clean_udid_by_app_obj e {e}")

    @staticmethod
    def clean_app_by_user_obj(app_obj):
        """
        该APP为超级签，删除app的时候，需要清理一下开发者账户里面的profile 和 bundleid
        :param app_obj:
        :return:
        """

        developer_id_lists = list(set(DeveloperAppID.objects.values_list("developerid").filter(app_id=app_obj)))

        for developer_id in developer_id_lists:
            developer_obj = AppIOSDeveloperInfo.objects.filter(pk=developer_id[0]).first()
            if developer_obj and (
                    developer_obj.user_id == app_obj.user_id or check_uid_has_relevant(developer_obj.user_id.uid,
                                                                                       app_obj.user_id.uid)):
                IosUtils.clean_super_sign_things_by_app_obj(app_obj, developer_obj)

    @staticmethod
    def clean_super_sign_things_by_app_obj(app_obj, developer_obj):
        IosUtils.clean_app_by_developer_obj(app_obj, developer_obj)
        delete_app_to_dev_and_file(developer_obj, app_obj.id)
        IosUtils.clean_udid_by_app_obj(app_obj, developer_obj)
        delete_app_profile_file(developer_obj, app_obj)

    @staticmethod
    def clean_app_by_developer_obj(app_obj, developer_obj):
        developer_app_id_obj = DeveloperAppID.objects.filter(developerid=developer_obj, app_id=app_obj).first()
        if developer_app_id_obj:
            app_api_obj = get_api_obj(developer_obj, app_obj)
            app_api_obj.del_profile(developer_app_id_obj.profile_id, app_obj.app_id)
            app_api_obj2 = get_api_obj(developer_obj, app_obj)
            app_api_obj2.del_app(developer_app_id_obj.aid, app_obj.bundle_id, app_obj.app_id)
            developer_app_id_obj.delete()

    @staticmethod
    def clean_developer(developer_obj, user_obj, delete_file=True):
        """
        根据消耗记录 删除该苹果账户下所有信息
        :param delete_file:
        :param user_obj:
        :param developer_obj:
        :return:
        """
        try:
            for APPToDeveloper_obj in APPToDeveloper.objects.filter(developerid=developer_obj):
                app_obj = APPToDeveloper_obj.app_id
                IosUtils.clean_app_by_developer_obj(app_obj, developer_obj)
                delete_app_to_dev_and_file(developer_obj, app_obj.id)
                IosUtils.clean_udid_by_app_obj(app_obj, developer_obj)
            if delete_file:
                full_path = file_format_path(user_obj, get_auth_form_developer(developer_obj))
                try:
                    # move dirs replace delete
                    new_full_path_dir = os.path.dirname(full_path)
                    new_full_path_name = os.path.basename(full_path)
                    new_full_path = os.path.join(os.path.dirname(new_full_path_dir),
                                                 '%s_%s_%s' % ('remove', new_full_path_name, get_format_time()))
                    os.rename(new_full_path_dir, new_full_path)
                except Exception as e:
                    logger.error("clean_developer developer_obj:%s user_obj:%s delete file failed Exception:%s" % (
                        developer_obj, user_obj, e))
            return True, 'success'
        except Exception as e:
            return False, {'err_info': str(e)}

    @staticmethod
    def get_developer_cert_info(developer_obj):
        """
        获取开发者证书信息
        :param developer_obj:
        :return:
        """
        app_api_obj = get_api_obj(developer_obj)
        # status, result = app_api_obj.get_developer_cert_info({'filter[certificateType]': 'IOS_DISTRIBUTION'})
        status, result = app_api_obj.get_developer_cert_info()
        if status:
            cert_info = []
            cert_is_exists = True
            for cert_obj in result:
                c_info = {
                    'certid': cert_obj.id,
                    'serial_number': cert_obj.serialNumber,
                    'name': cert_obj.name,
                    'display_name': cert_obj.displayName,
                    'platform': cert_obj.platform,
                    'cert_expire_time': format_apple_date(cert_obj.expirationDate),
                    'c_type': cert_obj.certificateType,
                    'exist': False}
                if cert_obj.id == developer_obj.certid and cert_is_exists:
                    developer_obj.cert_expire_time = format_apple_date(cert_obj.expirationDate)
                    cert_is_exists = False
                    c_info['exist'] = True
                cert_info.append(c_info)
                cert_info.sort(key=lambda x: x['exist'] == False)
            if developer_obj.certid and len(developer_obj.certid) > 3 and cert_is_exists and len(result) > 0:
                # 多次判断数据库证书id和苹果开发id不一致，可认为被用户删掉，需要执行清理开发者操作
                return status, {'return_info': '证书异常，苹果开发者证书与平台记录ID不一致', 'cert_info': cert_info}
            if developer_obj.certid and len(developer_obj.certid) > 3 and len(result) == 0:
                return status, {'return_info': '证书异常，苹果开发者证书为空，疑似证书在苹果开发平台被删除', 'cert_info': cert_info}
            return status, {'cert_info': cert_info}
        return status, result

    @staticmethod
    def active_developer(developer_obj, auto_clean=True, loop_count=1):
        """
        激活开发者账户
        :param loop_count:
        :param auto_clean:
        :param developer_obj:
        :return:
        """
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.get_developer_cert_info({'filter[certificateType]': 'IOS_DISTRIBUTION'})
        if status:
            cert_is_exists = True
            for cert_obj in result:
                if cert_obj.id == developer_obj.certid:
                    developer_obj.cert_expire_time = format_apple_date(cert_obj.expirationDate)
                    cert_is_exists = False
                    break
            developer_obj.status = AppleDeveloperStatus.ACTIVATED
            if developer_obj.certid and len(developer_obj.certid) > 3 and cert_is_exists and len(result) > 0:
                # 多次判断数据库证书id和苹果开发id不一致，可认为被用户删掉，需要执行清理开发者操作
                if loop_count > 3:
                    if auto_clean:
                        logger.warning(f"clean developer {developer_obj}")
                        IosUtils.clean_developer(developer_obj, developer_obj.user_id)
                        developer_obj.certid = None
                        developer_obj.cert_expire_time = None
                        # 捕获失败结果，三次重试之后，执行callback 方法，避免一次执行失败直接清理数据
                        developer_obj.status = AppleDeveloperStatus.CERTIFICATE_MISSING
                        developer_obj.save(update_fields=['certid', 'cert_expire_time', 'status'])
                        return False, {'return_info': '证书检测有误'}
                    else:
                        developer_obj.status = AppleDeveloperStatus.CERTIFICATE_MISSING
                        developer_obj.save(update_fields=['certid', 'cert_expire_time', 'status'])

                else:
                    loop_count += 1
                    logger.info(
                        f"{developer_obj} loop check developer cert.auto_clean:{auto_clean} loop_count:{loop_count}")
                    return IosUtils.active_developer(developer_obj, auto_clean, loop_count)

            if developer_obj.certid and len(developer_obj.certid) > 3 and len(result) == 0:
                developer_obj.status = AppleDeveloperStatus.CERTIFICATE_MISSING
                developer_obj.save(update_fields=['certid', 'cert_expire_time', 'status'])
                return False, {'return_info': '证书异常，苹果开发者证书为空，疑似证书在苹果开发平台被删除'}
            developer_obj.save(update_fields=['certid', 'cert_expire_time', 'status'])
        return status, result

    @staticmethod
    def create_developer_space(developer_obj, user_obj):
        auth = get_auth_form_developer(developer_obj)
        file_format_path_name = file_format_path(user_obj, auth)
        if not os.path.isdir(os.path.dirname(file_format_path_name)):
            os.makedirs(os.path.dirname(file_format_path_name))

    @staticmethod
    def create_developer_cert(developer_obj, user_obj):
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.create_cert(user_obj)
        if status:
            cert_id = result.id
            AppIOSDeveloperInfo.objects.filter(user_id=user_obj, issuer_id=developer_obj.issuer_id).update(
                status=AppleDeveloperStatus.ACTIVATED,
                certid=cert_id, cert_expire_time=format_apple_date(result.expirationDate))
            resign_app_obj = IosUtils.get_resign_obj(user_obj, developer_obj)
            resign_app_obj.make_p12_from_cert(cert_id)
        return status, result

    @staticmethod
    def revoke_developer_cert(developer_obj, user_obj):
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.revoke_cert()
        if not status:
            logger.warning('%s revoke cert failed,but i need clean cert_id %s' % (developer_obj.issuer_id, result))
        AppIOSDeveloperInfo.objects.filter(user_id=user_obj, issuer_id=developer_obj.issuer_id).update(
            status=AppleDeveloperStatus.CERTIFICATE_MISSING,
            certid=None, cert_expire_time=None)
        return status, result

    @staticmethod
    def check_developer_cert(developer_obj, user_obj):
        # 暂时无用
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.get_cert_obj_by_cid()
        if not status:
            AppIOSDeveloperInfo.objects.filter(user_id=user_obj, issuer_id=developer_obj.issuer_id).update(
                certid=None, cert_expire_time=None)
        return status, result

    @staticmethod
    def auto_get_cert_id_by_p12(developer_obj, user_obj):
        auth = get_auth_form_developer(developer_obj)
        app_api_obj = get_api_obj(developer_obj)
        file_format_path_name = file_format_path(user_obj, auth)
        app_dev_pem = file_format_path_name + ".pem.bak"
        status, result = app_api_obj.auto_set_certid_by_p12(app_dev_pem)
        if status:
            AppIOSDeveloperInfo.objects.filter(user_id=user_obj, issuer_id=auth.get("issuer_id")).update(
                status=AppleDeveloperStatus.ACTIVATED,
                certid=result.id, cert_expire_time=format_apple_date(result.expirationDate))
        return status, result

    @staticmethod
    def get_device_from_developer(developer_obj, err_return=False):
        app_api_obj = get_api_obj(developer_obj)
        status, result = app_api_obj.get_device()
        udid_developer_obj_list = UDIDsyncDeveloper.objects.filter(developerid=developer_obj).values_list('udid')
        udid_developer_list = [x[0] for x in udid_developer_obj_list if len(x) > 0]
        udid_result_list = []
        if status:
            udid_result_list = [device.udid for device in result]

        udid_same = set(udid_result_list) & set(udid_developer_list)
        if len(udid_result_list) > 0 and len(udid_developer_list) > 0:
            same_p = (len(udid_same) / len(udid_result_list) + len(udid_same) / len(udid_developer_list)) / 2
        else:
            same_p = 0
        # 获取设备列表的时候，有时候会发生灵异事件，尝试多次获取 【也可能是未知bug导致】【已经存在，获取的数据并不是该用户数据】
        if status and ((isinstance(result, list) and len(result) == 0) or same_p < 0.8):
            time.sleep(2)
            logger.warning(f'{developer_obj.issuer_id} get device may be wrong. try again. online result {result}')
            logger.warning(f'{developer_obj.issuer_id} get device may be wrong. db result {udid_developer_list}')
            status, result = app_api_obj.get_device()
        if status and developer_obj.issuer_id:

            status1, msg = IosUtils.check_device_status(developer_obj, result)
            if not status1 and err_return:
                return status1, {'return_info': msg}

            udid_result_list = [device.udid for device in result]
            udid_enabled_result_list = [device.udid for device in result if device.status == DeviceStatus.ENABLED]

            logger.warning(f"issuer_id:{developer_obj.issuer_id} udid database info: {udid_developer_list}")
            logger.warning(f"issuer_id:{developer_obj.issuer_id} udid develope info: {udid_result_list}")
            logger.warning(f"issuer_id:{developer_obj.issuer_id} udid develope enable info: {udid_enabled_result_list}")

            will_del_udid_list = list(set(udid_developer_list) - set(udid_result_list))
            logger.warning(f"issuer_id:{developer_obj.issuer_id} udidsync will delete: {will_del_udid_list}")

            will_del_disabled_udid_list = list(set(udid_developer_list) - set(udid_enabled_result_list))
            logger.warning(f"issuer_id:{developer_obj.issuer_id} delete and disabled: {will_del_disabled_udid_list}")

            for device_obj in result:
                obj, create = update_or_create_developer_udid_info(device_obj, developer_obj)
                if not create:
                    DeveloperDevicesID.objects.filter(udid=obj, developerid=developer_obj).update(
                        **{'did': device_obj.id})
            AppUDID.objects.filter(udid__udid__in=will_del_disabled_udid_list, udid__developerid=developer_obj).delete()
            developer_device_list = DeveloperDevicesID.objects.filter(udid__udid__in=will_del_disabled_udid_list,
                                                                      developerid=developer_obj).all()
            app_pk_list = []
            for developer_device_obj in developer_device_list:
                app_pk_list.append(developer_device_obj.app_id.pk)
                developer_device_obj.delete()

            for app_pk in list(set(app_pk_list)):
                app_obj = Apps.objects.filter(pk=app_pk).first()
                if APPSuperSignUsedInfo.objects.filter(developerid=developer_obj, app_id=app_obj).count() == 0:
                    logger.warning(f"issuer_id:{developer_obj.issuer_id} delete {app_obj} profile and sign ipa file")
                    IosUtils.clean_app_by_developer_obj(app_obj, developer_obj)
                    delete_app_to_dev_and_file(developer_obj, app_obj.pk)
                    delete_app_profile_file(developer_obj, app_obj)

            UDIDsyncDeveloper.objects.filter(udid__in=will_del_udid_list, developerid=developer_obj).delete()

            # 清理
            udids = [device.udid for device in result if device.status in [DeviceStatus.ENABLED, DeviceStatus.DISABLED]]
            DeviceAbnormalUDID.objects.filter(auto_remove=True,
                                              udid__developerid__user_id=developer_obj.user_id,
                                              udid__udid__in=udids).delete()

        return status, result
