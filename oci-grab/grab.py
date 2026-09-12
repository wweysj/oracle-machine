#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCI 免费 A1 实例容量轮询抢购脚本
用法: 配好环境变量后运行 python grab.py
成功创建实例后发送通知并退出(退出码 0)。
"""

import os
import random
import sys
import time
import urllib.parse
import urllib.request

try:
    import oci
except ImportError:
    sys.exit("缺少依赖: 请先执行  pip install oci")

# ---------- 可调参数(全部可用环境变量覆盖) ----------
OCPUS = float(os.environ.get("OCPUS", "2"))          # 默认 2 核(新免费配额)
MEMORY_GB = float(os.environ.get("MEMORY_GB", "12"))  # 默认 12G; 抢不到可降为 1核6G 提高成功率
INTERVAL = int(os.environ.get("INTERVAL_SECONDS", "300"))   # 轮询间隔, 默认 5 分钟
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "0"))     # 0 = 无限轮询
ADS = [a.strip() for a in os.environ.get("AVAILABILITY_DOMAINS", "").split(",") if a.strip()]

# ---------- 必填凭据 ----------
config = {
    "tenancy": os.environ["OCI_TENANCY"],
    "user": os.environ["OCI_USER"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "region": os.environ["OCI_REGION"],
    "key_content": os.environ["OCI_PRIVATE_KEY"].replace("\\n", "\n"),
}
COMPARTMENT = os.environ.get("COMPARTMENT_ID", config["tenancy"])
SUBNET_ID = os.environ["SUBNET_ID"]
IMAGE_ID = os.environ.get("IMAGE_ID", "")  # 留空则自动选用最新的 Ubuntu ARM 镜像
SSH_PUBLIC_KEY = os.environ.get("SSH_PUBLIC_KEY", "")
DISPLAY_NAME = os.environ.get("INSTANCE_NAME", "a1-free")

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")  # Server酱, 可选


def notify(title: str, body: str) -> None:
    """抢到后通知: Telegram + Server酱(可选), 失败不影响主流程。"""
    if TG_TOKEN and TG_CHAT:
        try:
            data = urllib.parse.urlencode(
                {"chat_id": TG_CHAT, "text": f"{title}\n{body}"}
            ).encode()
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, timeout=15
            )
            print("[notify] Telegram 已发送")
        except Exception as e:
            print(f"[notify] Telegram 发送失败: {e}")
    if SERVERCHAN_KEY:
        try:
            data = urllib.parse.urlencode(
                {"title": title, "desp": body}
            ).encode()
            urllib.request.urlopen(
                f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send", data=data, timeout=15
            )
            print("[notify] Server酱 已发送")
        except Exception as e:
            print(f"[notify] Server酱 发送失败: {e}")


def list_availability_domains():
    if ADS:
        return ADS
    identity = oci.identity.IdentityClient(config)
    return [ad.name for ad in identity.list_availability_domains(COMPARTMENT).data]


def resolve_image_id(compute) -> str:
    """IMAGE_ID 留空时, 自动查询该区域最新的 Ubuntu ARM (aarch64) 镜像。"""
    if IMAGE_ID:
        return IMAGE_ID
    imgs = compute.list_images(
        COMPARTMENT,
        operating_system="Canonical Ubuntu",
        shape="VM.Standard.A1.Flex",
        sort_by="TIMECREATED",
        sort_order="DESC",
    ).data
    img = next(i for i in imgs if "aarch64" in i.display_name.lower())
    print(f"未填 IMAGE_ID, 自动选用镜像: {img.display_name}")
    return img.id


def try_launch(compute, ad_name: str, image_id: str):
    details = oci.core.models.LaunchInstanceDetails(
        compartment_id=COMPARTMENT,
        availability_domain=ad_name,
        display_name=DISPLAY_NAME,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=OCPUS, memory_in_gbs=MEMORY_GB
        ),
        source_details=oci.core.models.InstanceSourceViaImageDetails(image_id=image_id),
        create_vnic_details=oci.core.models.CreateVnicDetails(subnet_id=SUBNET_ID, assign_public_ip=True),
        metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
    )
    return compute.launch_instance(details)


def main():
    ads = list_availability_domains()
    print(f"区域 {config['region']} 可用域: {ads}")
    print(f"目标配置: {OCPUS} OCPU / {MEMORY_GB}GB, 间隔 {INTERVAL}s")
    compute = oci.core.ComputeClient(config)
    image_id = resolve_image_id(compute)

    attempt = 0
    while True:
        attempt += 1
        for ad in ads:
            try:
                resp = try_launch(compute, ad)
                inst = resp.data
                msg = f"🎉 抢到了!\n实例: {inst.display_name}\nOCID: {inst.id}\n可用域: {ad}"
                print(msg)
                notify("OCI A1 抢购成功", msg)
                return 0
            except oci.exceptions.ServiceError as e:
                status = e.status
                msg = (e.message or "").lower()
                if status in (500, 429) or "capacity" in msg or "limit" in msg and "out" in msg:
                    print(f"[{time.strftime('%H:%M:%S')}] #{attempt} {ad}: 容量不足({status}), 继续等")
                elif status == 404 and "out of host capacity" in msg:
                    print(f"[{time.strftime('%H:%M:%S')}] #{attempt} {ad}: 容量不足, 继续等")
                else:
                    # 凭据错误/配额用尽/参数错误等, 重试无意义
                    err = f"致命错误 status={status}: {e.message}"
                    print(err)
                    notify("OCI 抢购脚本停止", err)
                    return 1
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] #{attempt} {ad}: 异常 {e}, 继续等")

        if MAX_ATTEMPTS and attempt >= MAX_ATTEMPTS:
            print("已达最大尝试次数, 退出")
            return 1
        # 间隔 ±20% 抖动, 避免请求过于规律
        time.sleep(int(INTERVAL * random.uniform(0.8, 1.2)))


if __name__ == "__main__":
    sys.exit(main())
