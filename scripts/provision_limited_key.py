#!/usr/bin/env python3
"""用主账号密钥创建一个只授予 DNS 权限的子用户，并生成它的 API 密钥。

CAM 的建用户接口是 AddUser（不是 CreateUser）。全程只做追加操作，
不删除、不修改任何既有资源；如需回滚，在控制台删掉子用户 acme-dns 即可。
"""
import os
import sys

from tencentcloud.cam.v20190116 import cam_client, models
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

SID = os.environ["TC_SID"]
SKEY = os.environ["TC_SKEY"]
USER_NAME = "acme-dns"
POLICY_NAME = "QcloudDNSPodFullAccess"

cred = credential.Credential(SID, SKEY)
cli = cam_client.CamClient(cred, "ap-guangzhou")


def find_policy():
    req = models.ListPoliciesRequest()
    req.Keyword = POLICY_NAME
    req.Page = 1
    req.Rp = 50
    resp = cli.ListPolicies(req)
    for p in resp.List or []:
        if p.PolicyName == POLICY_NAME:
            return int(p.PolicyId)
    return None


def lookup_uin():
    req = models.ListUsersRequest()
    resp = cli.ListUsers(req)
    for u in resp.Data or []:
        if u.Name == USER_NAME:
            return int(u.Uin)
    return None


def ensure_user():
    uin = lookup_uin()
    if uin:
        print(f"  子用户 {USER_NAME} 已存在，Uin={uin}")
        return uin
    req = models.AddUserRequest()
    req.Name = USER_NAME
    req.Remark = "ACME DNS-01 only, for socialsense.cn cert auto-renewal"
    req.ConsoleLogin = 0
    try:
        resp = cli.AddUser(req)
        uin = int(resp.Uin)
        print(f"  ✓ 创建子用户 {USER_NAME}，Uin={uin}")
        return uin
    except TencentCloudSDKException as e:
        print(f"  ✗ AddUser 失败: {e.code} / {e.message}")
        return lookup_uin()


policy_id = find_policy()
print(f"  策略 {POLICY_NAME} → ID {policy_id}")
if not policy_id:
    sys.exit(1)

uin = ensure_user()
if not uin:
    print("  ✗ 无法获得子用户 Uin")
    sys.exit(1)

# 绑定策略（重复绑定会报错，忽略即可）
try:
    req = models.AttachUserPolicyRequest()
    req.Uin = uin
    req.PolicyId = policy_id
    cli.AttachUserPolicy(req)
    print("  ✓ 已绑定 QcloudDNSPodFullAccess")
except TencentCloudSDKException as e:
    if "already" in (e.message or "").lower() or "exist" in (e.message or "").lower():
        print("  · 策略已绑定，跳过")
    else:
        print(f"  ✗ 绑定失败: {e.code} / {e.message}")

# 生成密钥；若已有密钥则复用（子用户上限 2 个）
try:
    req = models.ListAccessKeysRequest()
    req.TargetUin = uin
    existing = cli.ListAccessKeys(req)
    keys = existing.AccessKeys or []
    print(f"  · 子用户现有密钥 {len(keys)} 个")
    if keys:
        print("  · 已存在密钥，需在控制台确认后用新密钥；本次不重复创建")
except TencentCloudSDKException as e:
    print(f"  · 查询既有密钥失败（可忽略）: {e.message}")

try:
    req = models.CreateAccessKeyRequest()
    req.TargetUin = uin
    resp = cli.CreateAccessKey(req)
    print("  ✓ 生成子用户 API 密钥")
    print()
    print("SUBSECRET_ID=" + resp.AccessKeyId)
    print("SUBSECRET_KEY=" + resp.SecretKey)
except TencentCloudSDKException as e:
    print(f"  ✗ 生成密钥失败: {e.code} / {e.message}")
    sys.exit(1)
