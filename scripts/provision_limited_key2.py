#!/usr/bin/env python3
"""修正版：绑定 DNS 策略 + 删除拿不到 Secret 的旧密钥 + 重新生成并输出新密钥。

字段名踩坑记录（腾讯云 CAM）：
  - 绑策略参数是 AttachUin，不是 Uin
  - CreateAccessKey 返回的是 AccessKey 对象（内含 AccessKeyId / SecretKey），
    不是顶层 AccessKeyId；SecretKey 只在创建时返回一次，取不到就只能删了重建
"""
import json
import os
import sys

from tencentcloud.cam.v20190116 import cam_client, models
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

SID = os.environ["TC_SID"]
SKEY = os.environ["TC_SKEY"]
UIN = int(os.environ["TC_UIN"])
POLICY_ID = int(os.environ["TC_POLICY_ID"])

cred = credential.Credential(SID, SKEY)
cli = cam_client.CamClient(cred, "ap-guangzhou")

# ---- 1. 绑定 DNS 策略（AttachUin）----
try:
    req = models.AttachUserPolicyRequest()
    req.AttachUin = UIN
    req.PolicyId = POLICY_ID
    cli.AttachUserPolicy(req)
    print("  ✓ 已绑定 QcloudDNSPodFullAccess")
except TencentCloudSDKException as e:
    print(f"  · 绑定返回: {e.code} / {e.message}（已存在可忽略）")

# ---- 2. 列出现有密钥，删掉取不到 Secret 的那个 ----
try:
    req = models.ListAccessKeysRequest()
    req.TargetUin = UIN
    resp = cli.ListAccessKeys(req)
    keys = resp.AccessKeys or []
    print(f"  · 现有密钥 {len(keys)} 个")
    for k in keys:
        print(f"    - {k.AccessKeyId}  {k.Status}")
        try:
            d = models.DeleteAccessKeyRequest()
            d.AccessKeyId = k.AccessKeyId
            d.TargetUin = UIN
            cli.DeleteAccessKey(d)
            print(f"      已删除")
        except TencentCloudSDKException as e:
            print(f"      删除失败: {e.code} / {e.message}")
except TencentCloudSDKException as e:
    print(f"  · 列出密钥失败: {e.message}")

# ---- 3. 重新生成，完整 dump 返回 ----
try:
    req = models.CreateAccessKeyRequest()
    req.TargetUin = UIN
    resp = cli.CreateAccessKey(req)
    raw = json.loads(resp.to_json_string())
    print("  ✓ 已生成新密钥，原始返回：")
    print(json.dumps(raw, ensure_ascii=False, indent=2))
    ak = raw.get("AccessKey") or {}
    if ak.get("SecretKey"):
        print()
        print("SUBSECRET_ID=" + ak["AccessKeyId"])
        print("SUBSECRET_KEY=" + ak["SecretKey"])
except TencentCloudSDKException as e:
    print(f"  ✗ 生成失败: {e.code} / {e.message}")
    sys.exit(1)
