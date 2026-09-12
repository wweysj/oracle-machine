# OCI 免费 A1 实例自动抢购（GitHub Actions 方案）

甲骨文免费层 ARM 实例（A1.Flex）在热门区域常年 "Out of capacity"。本方案用 GitHub Actions 免费定时任务反复尝试创建实例，一旦有容量立即开成功并发 Telegram 通知，无需自己的电脑开机。

> 当前免费配额：**A1.Flex 2 OCPU / 12GB 内存**（老账户是 4核24G）。抢不到时可降为 1核6G，成功率更高。

## 文件说明

| 文件 | 作用 |
|---|---|
| `oci-grab/grab.py` | 抢购脚本：多可用域轮询、失败自动重试、成功后 Telegram/Server酱 通知 |
| `.github/workflows/grab.yml` | 定时工作流：每 30 分钟触发一次（GitHub 排队会有几分钟延迟，属正常） |

## 一、获取 OCI 凭据（约 10 分钟）

1. **创建 API Key**
   登录 [OCI 控制台](https://cloud.oracle.com) → 右上角头像 → **User Settings**（我的个人资料）→ **API Keys** → **Add API Key** → 选 *Generate API Key Pair*，**下载私钥文件**（`.pem`，只显示一次），页面上会显示指纹（Fingerprint）。

2. **收集 OCID**
   同一页面复制：
   - `OCI_USER`：用户 OCID（`ocid1.user.oc1...`）
   - `OCI_TENANCY`：租户 OCID（页面下方_tenancy_处）
   - `OCI_REGION`：右上角区域名（如 `ap-tokyo-1`、`ap-seoul-1`）
   - `OCI_FINGERPRINT`：刚生成 Key 的指纹

3. **获取网络与镜像 OCID**
   - **SUBNET_ID**： Networking → Virtual Cloud Networks → 你的 VCN → Subnets → 复制子网 OCID（没有 VCN 就先建一个）
   - **IMAGE_ID**：Compute → Instances → Create Instance 页面上能看到 Canonical Ubuntu / Oracle Linux 的镜像 OCID；也可用 OCI CLI `oci compute image list --operating-system "Canonical Ubuntu" ...` 查询
   - **SSH_PUBLIC_KEY**：你本机的公钥 `cat ~/.ssh/id_rsa.pub`（没有就 `ssh-keygen` 生成），开成功后用它登录

4. **（可选）COMPARTMENT_ID / INSTANCE_NAME**
   不填默认用租户根区间和实例名 `a1-free`。

## 二、配置 GitHub Secrets

在你的 GitHub 仓库 → **Settings → Secrets and variables → Actions → New repository secret**，逐条添加：

| Secret 名 | 通俗叫法 | 必填 | 说明 |
|---|---|---|---|
| `OCI_TENANCY` | 租户编号 | ✅ | 租户 OCID |
| `OCI_USER` | 用户编号 | ✅ | 用户 OCID |
| `OCI_FINGERPRINT` | 密钥指纹 | ✅ | API Key 指纹 |
| `OCI_REGION` | 区域代码 | ✅ | 区域，如 `ap-seoul-1` |
| `OCI_PRIVATE_KEY` | API私钥内容 | ✅ | **私钥完整内容**（包括 `-----BEGIN PRIVATE KEY-----` 首尾行，直接整个粘贴） |
| `SUBNET_ID` | 子网编号 | ✅ | 子网 OCID |
| `IMAGE_ID` | 镜像编号 | 可选 | 留空则自动选用最新的 Ubuntu ARM (aarch64) 镜像 |
| `SSH_PUBLIC_KEY` | SSH公钥 | ✅ | SSH 公钥内容 |
| `COMPARTMENT_ID` | 区间编号 | 可选 | 区间 OCID，默认租户 |
| `INSTANCE_NAME` | 实例名字 | 可选 | 实例名，默认 `a1-free` |
| `OCPUS` | CPU核数 | 可选 | 默认 `2`；抢不到改 `1` |
| `MEMORY_GB` | 内存大小 | 可选 | 默认 `12`；保守可改 `6` |
| `TELEGRAM_BOT_TOKEN` | TG机器人令牌 | 可选 | @BotFather 建 Bot 获取 |
| `TELEGRAM_CHAT_ID` | TG聊天编号 | 可选 | @userinfobot 查自己的 ID |
| `SERVERCHAN_KEY` | Server酱密钥 | 可选 | [Server酱](https://sct.ftqq.com) SendKey，微信通知 |

通知至少配一组（Telegram 或 Server酱），也可以都不配只看 Actions 日志。

## 三、启用与验证

1. 把本目录的 `.github/workflows/grab.yml` 和 `oci-grab/grab.py` 推到 GitHub 仓库。
2. 仓库 **Actions** 页签 → 启用 workflow → 选中 *OCI A1 Grab* → **Run workflow** 手动触发一次。
3. 看日志：
   - 出现 `容量不足(500/429), 继续等` → 一切正常，等定时任务慢慢试
   - 出现 `致命错误 status=...` → 修正对应凭据或配置后重试
   - 日志出现 `🎉 抢到了!` + 收到 Telegram 通知 → 去控制台关掉定时任务（删掉/禁用 workflow），避免继续运行

## 四、本地运行（可选，备用）

```bash
pip install oci
export OCI_TENANCY=ocid1.tenancy.oc1...
export OCI_USER=ocid1.user.oc1...
export OCI_FINGERPRINT=xx:xx:...
export OCI_REGION=ap-seoul-1
export OCI_PRIVATE_KEY="$(cat 私钥.pem)"
export SUBNET_ID=ocid1.subnet.oc1...
export IMAGE_ID=ocid1.image.oc1...
export SSH_PUBLIC_KEY="$(cat ~/.ssh/id_rsa.pub)"
python oci-grab/grab.py
```

## 提高成功率的小技巧

- **降配**：1 OCPU + 6GB 比 2核12G 容易开得多，先抢到再在控制台改配置（改配同样可能缺容量，但概率高很多）。
- **换区域**：东京/首尔/新加坡竞争大，可试试 Osaka、Chuncheon、Osaka 等冷门区。开通区域后脚本里改 `OCI_REGION` 即可。
- **别把间隔调太短**：脚本默认 30 分钟一次 + 随机抖动，已足够且安全。频繁高频请求有封号风险，社区已有多例。
- **PAYG**：升级"即付即用"仍免费用免费配额，但开容量优先级显著更高，是"急用"的最有效手段。

## 风险提示

- 免费层实例 7 天内若持续 100% CPU 空闲等"闲置"状态可能被回收，开成功后记得部署点东西（哪怕一个网页）。
- 私钥放 GitHub Secrets 是加密的，但请勿在日志里打印凭据；脚本已确保不输出任何密钥内容。
