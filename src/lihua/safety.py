"""安全分层引擎：黑 / 白 / 灰 三层分类。

设计原则：
1. 黑名单（black）：硬 ban，绝不执行。优先级最高。
2. 白名单（white）：自动执行，不问用户。
3. 灰名单（grey）：用人类语言确认，不展示原始命令。
4. 未知（unknown）：默认按灰名单处理（最保守）。

优先级：black > grey > white > unknown
（只要命令中包含任何黑/灰名单成分，整条命令按最严级别处理）
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Literal

SafetyLevel = Literal["black", "grey", "white", "unknown"]


@dataclass
class SafetyDecision:
    """安全引擎对一条命令的分类结果。"""

    level: SafetyLevel
    rule: str = ""
    reason: str = ""
    human_message: str | None = None
    auto_execute: bool = False
    sub_decisions: list["SafetyDecision"] | None = None

    @property
    def allowed(self) -> bool:
        return self.level != "black"


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------

# 黑名单：正则 + 中文解释
# 注意：这些正则会同时用于"整体命令"和"拆分后的子命令"检测，
# 所以像 curl|bash、fork bomb 这种含分隔符的危险模式
# 会在拆分前先被整体匹配（见 classify() 函数）。
_BLACKLIST: list[tuple[str, str]] = [
    # rm -rf / 及变种
    (r"rm\s+(?:-\w+\s+)*--no-preserve-root",
     "rm --no-preserve-root 会删除根目录"),
    (r"rm\s+(?:-\w*r\w*\s+)+/(\s|$)",
     "rm -rf / 会删除整个系统"),
    (r"rm\s+(?:-\w*r\w*\s+)+/\*",
     "rm -rf /* 会删除根目录所有文件"),
    (r"rm\s+(?:-\w*r\w*\s+)+/(?:boot|etc|usr|var|bin|sbin|lib|sys|proc|dev|home|root|opt|srv)(?:\s|$)",
     "rm -rf 会删除关键系统目录"),
    # 裸磁盘写入
    (r"dd\s+if=\S+\s+of=/dev/(?:sd|nvme|vd|hd|mmcblk)", "dd 会写入裸磁盘，破坏数据"),
    (r"dd\s+of=/dev/(?:sd|nvme|vd|hd|mmcblk)", "dd 会写入裸磁盘，破坏数据"),
    (r"mkfs(?:\.\w+)?\s+/dev/", "mkfs 会格式化磁盘分区"),
    (r">\s*/dev/(?:sd|nvme|vd|hd|mmcblk)", "重定向到裸磁盘会破坏数据"),
    (r"mkswap\s+/dev/(?:sd|nvme|vd)", "mkswap 会破坏磁盘数据"),
    (r"fdisk\s+/dev/(?:sd|nvme|vd)", "fdisk 会修改分区表"),
    (r"parted\s+/dev/(?:sd|nvme|vd)", "parted 会修改分区表"),
    (r"wipefs\s+-[aA]\s+/dev/", "wipefs 会清除分区签名"),
    (r">\s*/dev/mem", "写 /dev/mem 会让系统崩溃"),
    # fork bomb（含 | 和 & 字符，必须整体匹配）
    (r":\s*\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",
     "fork bomb 会让系统卡死"),
    # 权限失控
    (r"chmod\s+-R\s+777\s+/", "chmod -R 777 / 会让整个系统权限失控"),
    (r"chown\s+-R\s+\S+\s+/", "chown -R / 会改整个系统属主"),
    # init 0/6 隐蔽关机命令（保留黑名单，防止 AI 误执行）
    (r"\binit\s+0\b", "init 0 会直接关机"),
    (r"\binit\s+6\b", "init 6 会直接重启"),
    # 杀进程
    (r"kill\s+-9\s+-1", "kill -9 -1 会杀死所有用户进程"),
    (r"kill(?:all)?\s+-9\s+1\b", "杀 init 进程会让系统崩溃"),
    # 远程脚本执行（含 |，必须整体匹配）
    (r"curl\s+[^|]*\|\s*(?:sh|bash|zsh|fish)",
     "curl | sh 远程执行脚本，安全风险极高"),
    (r"wget\s+[^|]*\|\s*(?:sh|bash|zsh|fish)",
     "wget | sh 远程执行脚本，安全风险极高"),
    # 内核模块
    (r"modprobe\s+-r\s+(?:ext4|btrfs|xfs|vfat|ntfs)",
     "卸载文件系统模块会让磁盘无法挂载"),
    # shred 覆写整个磁盘
    (r"shred\s+.*?/dev/(?:sd|nvme|vd|hd|mmcblk)",
     "shred 覆写整个磁盘，数据将永久丢失"),
    # 危险的 sed 直接写入系统关键文件
    (r"sed\s+-i.*\s+/etc/(?:passwd|shadow|sudoers|fstab|grub)",
     "直接修改关键系统文件可能导致系统无法启动"),
    # v0.8.1: LLM 常见危险模式（run_shell 万能工具引入后的防护）
    # find 配合删除——LLM 可能用 find -delete 批量删文件
    (r"find\s+/(?:\s|$).*-delete",
     "find / -delete 会递归删除根目录下的文件"),
    (r"find\s+/(?:\s|$).*-exec\s+rm",
     "find / -exec rm 会递归删除根目录下的文件"),
    (r"find\s+/(?:\s|$).*-exec\s+shred",
     "find / -exec shred 会递归覆写根目录下的文件"),
    # mv 到 /dev/null——LLM 可能用 mv 清空文件
    (r"mv\s+\S+\s+/dev/null",
     "mv 到 /dev/null 会永久丢失文件"),
    # cp /dev/zero 到裸磁盘——和 dd 类似的破坏
    (r"cp\s+/dev/zero\s+/dev/(?:sd|nvme|vd|hd|mmcblk)",
     "cp /dev/zero 到磁盘会覆写所有数据"),
    # chmod 777 关键系统文件——LLM 可能为了"解决权限问题"改 /etc 权限
    (r"chmod\s+(?:-R\s+)?777\s+/etc/(?:passwd|shadow|sudoers|fstab|grub)",
     "chmod 777 关键系统文件会导致权限失控"),
    (r"chmod\s+-R\s+777\s+/(?:boot|etc|usr|var|bin|sbin|lib|sys|proc|dev|root|opt|srv)",
     "chmod -R 777 系统目录会让权限失控"),
    (r"chmod\s+-R\s+777\s+~",
     "chmod -R 777 ~ 会让家目录所有文件权限失控"),
    (r"chmod\s+-R\s+777\s+/home",
     "chmod -R 777 /home 会让所有用户家目录权限失控"),
    # 启用 SysRq——LLM 不应该碰内核调试接口
    (r">\s*/proc/sys/kernel/sysrq",
     "修改 SysRq 会暴露内核调试接口"),
    # 关机/重启——LLM 不应该直接关机或重启用户机器
    (r"\bshutdown\b(?:\s|-)",
     "shutdown 会关机，LLM 不应直接执行"),
    (r"\bpoweroff\b(?:\s|$)",
     "poweroff 会关机，LLM 不应直接执行"),
    (r"\breboot\b(?:\s|$)",
     "reboot 会重启，LLM 不应直接执行"),
    # 写 /boot——LLM 不应该改内核或引导
    (r">\s*/boot/",
     "写 /boot 目录可能破坏系统引导"),
    # iptables -F——清空防火墙规则会让系统暴露
    (r"\biptables\s+-F\b",
     "iptables -F 会清空防火墙规则，让系统暴露"),
    (r"\bip6tables\s+-F\b",
     "ip6tables -F 会清空 IPv6 防火墙规则"),
    # systemctl stop 关键服务——LLM 不应该停 SSH/网络
    (r"systemctl\s+stop\s+(?:ssh|sshd|NetworkManager|networking|systemd-networkd)",
     "停止关键系统服务会导致断网或无法远程登录"),
]


# 灰名单：正则 + 中文描述模板（用 {arg} 占位符表示参数）
_GREYLIST: list[tuple[str, str, str]] = [
    # (pattern, reason, human_template)
    (r"^\s*sudo\s+(.+)", "需要管理员权限", "需要管理员权限来执行：{0}"),
    # v0.8.0: pkexec 和 sudo 同等——v0.7.13 替换 sudo→pkexec 时遗漏了灰名单
    (r"^\s*pkexec\s+(.+)", "需要管理员权限", "需要管理员权限来执行：{0}"),
    (r"apt(?:-get)?\s+purge\s+(\S+)", "卸载软件包并删配置",
     "卸载软件包 {0}（同时删除配置文件）"),
    (r"apt(?:-get)?\s+remove\s+(\S+)", "卸载软件包", "卸载软件包 {0}"),
    (r"apt(?:-get)?\s+autoremove", "自动清理不需要的包",
     "自动清理不需要的软件包"),
    (r"flatpak\s+uninstall\s+(?:--delete-data\s+)?(\S+)",
     "卸载 Flatpak 应用", "卸载 Flatpak 应用 {0}"),
    (r"snap\s+remove\s+(\S+)", "卸载 Snap 应用", "卸载 Snap 应用 {0}"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/etc/", "删除系统配置目录下的文件",
     "删除系统配置文件"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/var/", "删除系统数据目录下的文件",
     "删除系统数据文件"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/usr/", "删除系统程序文件",
     "删除系统程序文件"),
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*\s+/boot/", "删除启动文件",
     "删除系统启动文件"),
    (r"nmcli\s+connection\s+(?:modify|delete|add)", "修改网络连接配置",
     "修改网络连接配置"),
    (r"ip\s+(?:addr\s+add|addr\s+del|route\s+add|route\s+del)",
     "修改网络地址或路由", "修改网络地址或路由配置"),
    (r"systemctl\s+(?:stop|disable|mask|restart)\s+(?!--user)",
     "控制系统级服务", "控制系统级服务"),
    (r"gsettings\s+reset\s+", "重置桌面设置", "重置桌面设置项"),
    (r"dconf\s+reset\s+", "重置桌面配置", "重置桌面配置项"),
    (r"\bsu\b\s+", "切换到 root 用户", "切换到 root 用户"),
    (r"update-grub", "更新启动菜单", "更新系统启动菜单"),
    (r"grub-install", "重写启动引导", "重写系统启动引导"),
    (r"mount\s+/dev/", "挂载磁盘分区", "挂载磁盘分区"),
    (r"umount\s+/", "卸载文件系统", "卸载文件系统"),
    (r"tee\s+/etc/", "写入系统配置文件", "写入系统配置文件"),
    (r"cp\s+.+\s+/etc/", "复制到系统配置目录", "复制文件到系统配置目录"),
    (r"mv\s+.+\s+/etc/", "移动到系统配置目录", "移动文件到系统配置目录"),
    (r"pip3?\s+install\s+--user", "安装用户级 Python 包",
     "安装 Python 包到用户目录"),
    (r"pip3?\s+uninstall", "卸载 Python 包", "卸载 Python 包"),
    (r"npm\s+(?:install|uninstall)\s+-g", "全局安装/卸载 npm 包",
     "全局安装/卸载 npm 包"),
    (r"flushall", "清空 Redis 数据", "清空 Redis 所有数据"),
    (r"git\s+push\s+(?:-f|--force)", "强推 git 历史",
     "强推覆盖远程 git 历史"),
    # 关机/重启/休眠（用户确认后可执行）
    (r"\bshutdown\b", "关机", "关闭系统（关机）"),
    (r"\breboot\b", "重启", "重启系统"),
    (r"\bhalt\b", "关机", "关闭系统（halt）"),
    (r"\bpoweroff\b", "关机", "关闭系统（poweroff）"),
    (r"systemctl\s+(?:poweroff|reboot|halt|suspend|hibernate|hybrid-sleep)\b",
     "电源管理", "电源管理操作（关机/重启/休眠）"),
    (r"(?:^|sudo\s+)passwd\b(?:\s+(\S+))?", "修改用户密码", "修改用户密码"),
    (r"\btimedatectl\s+set-timezone\b", "修改系统时区", "修改系统时区"),
    (r"\blocale-gen\b", "重新生成语言环境", "重新生成系统语言环境"),
    (r"\bupdate-locale\b", "更新语言环境配置", "更新系统语言环境配置"),
    (r"\buseradd\b\s+", "添加系统用户", "添加系统用户"),
    (r"\buserdel\b\s+", "删除系统用户", "删除系统用户"),
    (r"\busermod\b\s+", "修改用户属性", "修改用户属性"),
    (r"\bgroupadd\b\s+", "添加用户组", "添加用户组"),
    (r"\bgroupdel\b\s+", "删除用户组", "删除用户组"),
    (r"\bchpasswd\b", "批量改密码", "批量修改用户密码"),
    (r"\bufw\s+(?:enable|disable|allow|deny|reject|reset)\b",
     "修改防火墙规则", "修改防火墙规则"),
    (r"\bip6tables\b", "修改 IPv6 防火墙", "修改 IPv6 防火墙规则"),
    (r"\biptables\b", "修改防火墙规则", "修改防火墙规则"),
    (r"\bnft\b\s+", "修改 nftables 防火墙", "修改 nftables 防火墙规则"),
    (r"\bsystemctl\s+(?:stop|disable|mask|restart|enable)\s+(?!--user)",
     "控制系统级服务", "控制系统级服务"),
    (r"\bsystemctl\s+set-default\b", "修改默认启动目标",
     "修改系统默认启动目标"),
    (r"\bhostnamectl\s+set-hostname\b", "修改系统主机名",
     "修改系统主机名"),
    (r"\bhwclock\b\s+--", "修改硬件时钟", "修改硬件时钟"),
    (r"\btzdata-update\b", "更新时区数据", "更新系统时区数据"),
    (r"\bbluetoothctl\s+(?:power|connect|disconnect|pair|trust|remove)\b",
     "修改蓝牙设置", "修改蓝牙设置"),
    (r"\brfkill\b\s+(?:block|unblock)\b", "修改无线设备状态",
     "开关无线设备（WiFi/蓝牙）"),
    (r"\bnmcli\s+(?:connection\s+delete|device\s+disconnect|radio\s+\w+\s+off)",
     "断开网络连接", "断开网络连接"),
    (r"\bdpkg-reconfigure\b", "重新配置软件包", "重新配置软件包"),
    (r"\bapt-mark\s+(?:hold|unhold)\b", "锁定/解锁软件包版本",
     "锁定或解锁软件包版本"),
    (r"\bupdate-alternatives\s+(?:--install|--set|--remove)\b",
     "修改默认程序", "修改系统默认程序"),
    (r"\bxrandr\s+--output\s+\S+\s+--(?:off|mode|rate|pos)",
     "修改屏幕显示", "修改屏幕显示设置"),
    (r"\bwpaperd\b", "修改壁纸", "修改桌面壁纸"),
    (r"\bnitrogen\b\s+--set", "修改壁纸", "修改桌面壁纸"),
    (r"\bfeh\b\s+--bg-", "修改壁纸", "修改桌面壁纸"),
    (r"\blpadmin\b\s+-p\s+\S+\s+-", "修改打印机配置", "修改打印机配置"),
    (r"\blpoptions\b\s+-p\s+\S+\s+-o\s+", "修改打印机选项",
     "修改打印机选项"),
    (r"\bcupsaccept\b|\bcupsreject\b", "控制打印队列",
     "控制打印队列接受/拒绝任务"),
    (r"\bmodprobe\b\s+(?!--)(?!-r\s+(?:ext4|btrfs|xfs|vfat|ntfs))",
     "加载内核模块", "加载内核模块"),
    (r"\bmodprobe\s+-r\b", "卸载内核模块", "卸载内核模块"),
    (r"\bsysctl\s+-w\b", "修改内核参数", "修改内核运行时参数"),
    (r"\bswapon\b\s+/", "启用交换分区", "启用交换分区"),
    (r"\bswapoff\b\s+/", "禁用交换分区", "禁用交换分区"),
    (r"\bfstrim\b\s+/", "TRIM SSD", "对 SSD 执行 TRIM 操作"),
    (r"\bbadblocks\b\s+/dev/", "检查磁盘坏块", "检查磁盘坏块（耗时较长）"),
    (r"\bsmartctl\b\s+-t\s+", "硬盘自检", "启动硬盘自检"),
    (r"\bchmod\b\s+[0-7]+\s+/(?:etc|var|usr|boot|root|home)",
     "修改系统目录权限", "修改系统目录权限"),
    (r"\bchown\b\s+\S+\s+/(?:etc|var|usr|boot|root|home)",
     "修改系统目录属主", "修改系统目录属主"),
    (r"\btee\b\s+/(?:etc|var|usr|boot)/", "写入系统文件",
     "写入系统文件"),
    (r"\bdd\b\s+if=", "dd 磁盘写入", "dd 磁盘写入（高风险操作）"),
    # v0.5.0 新增 Skill 的灰名单命令
    # rsync 实际同步（非 --dry-run / --version / -avn）
    (r"\brsync\b\s+(?!.*--dry-run)(?!.*--version)(?!.*-avn)",
     "rsync 文件同步", "rsync 同步文件（可能覆盖目标）"),
    # gpg 加密/解密
    (r"\bgpg\b\s+-[ced]\b", "gpg 加密/解密文件", "加密或解密文件"),
    (r"\bgpg\b\s+--(?:encrypt|decrypt)", "gpg 加密/解密文件",
     "加密或解密文件"),
    # shred 安全删除文件（非 /dev/）
    (r"\bshred\b\s+(?!.*\s/dev/(?:sd|nvme|vd|hd|mmcblk))",
     "安全删除文件（覆写后删除）", "安全删除文件（不可恢复）"),
    # git config 修改全局配置
    (r"\bgit\s+config\s+--global\b", "修改 git 全局配置",
     "修改 git 全局配置"),
    (r"\bgit\s+config\s+--(?:add|unset|replace-all)\b",
     "修改 git 配置", "修改 git 配置项"),
    # docker 容器操作
    (r"\bdocker\s+(?:pull|run|stop|rm|rmi|exec|kill|restart)\b",
     "Docker 容器操作", "操作 Docker 容器"),
    (r"\bdocker\s+container\s+(?:start|stop|rm|kill)\b",
     "Docker 容器操作", "操作 Docker 容器"),
    (r"\bdocker\s+image\s+(?:rm|prune|build|tag)\b",
     "Docker 镜像操作", "操作 Docker 镜像"),
    # python venv 创建
    (r"\bpython3?\s+-m\s+venv\b", "创建 Python 虚拟环境",
     "创建 Python 虚拟环境"),
    # ssh 密钥生成与拷贝（排除 -l 查看指纹 / -y 导出公钥 / --help）
    (r"\bssh-keygen\b\s+(?!-l\b)(?!-y\b)(?!--help\b)",
     "生成 SSH 密钥", "生成 SSH 密钥"),
    (r"\bssh-copy-id\b", "拷贝 SSH 公钥到远程", "拷贝 SSH 公钥到远程主机"),
    # VPN 连接
    (r"\bwg-quick\s+(?:up|down)\b", "WireGuard VPN 操作",
     "启动/停止 WireGuard VPN"),
    (r"\bopenvpn\s+--config\b", "OpenVPN 连接", "启动 OpenVPN 连接"),
    (r"\bopenvpn\s+--daemon\b", "OpenVPN 后台连接",
     "后台启动 OpenVPN"),
    # nmcli 热点
    (r"\bnmcli\s+device\s+wifi\s+hotspot\b", "创建 WiFi 热点",
     "创建 WiFi 热点"),
    # crontab 修改
    (r"\bcrontab\s+-[er]\b", "修改定时任务", "编辑或删除定时任务"),
    (r"\|\s*crontab\s+-\s*$", "添加定时任务", "添加定时任务到 crontab"),
    # samba 配置修改
    (r"\bte?e\s+-a\s+/etc/samba/", "修改 Samba 配置",
     "写入 Samba 配置文件"),
    # clamav 病毒库更新
    (r"\bfreshclam\b", "更新病毒库", "更新 ClamAV 病毒库"),
    # 显卡驱动安装与切换
    (r"\bubuntu-drivers\s+(?:autoinstall|install)\b",
     "安装显卡驱动", "安装显卡驱动（需重启）"),
    (r"\bprime-select\b\s+(?!-?-query\b)\S+",
     "切换显卡", "切换显卡（需注销重新登录）"),
    # 内核清理
    (r"\bapt(?:-get)?\s+autoremove\s+--purge\s+linux-",
     "清理旧内核", "清理旧内核（保留当前内核）"),
    # sed 修改系统配置
    (r"\bsed\s+-i\b.*\s+/etc/", "修改系统配置文件",
     "修改系统配置文件"),
    # add-apt-repository
    (r"\badd-apt-repository\b", "添加/删除 apt 仓库",
     "添加或删除 apt 仓库"),
    # flatpak remote-add/delete
    (r"\bflatpak\s+remote-(?:add|delete)\b", "修改 Flatpak 仓库",
     "添加或删除 Flatpak 仓库"),
    # snap switch/refresh
    (r"\bsnap\s+(?:switch|refresh|remove)\b", "Snap 操作",
     "切换或更新 Snap 应用"),
    # dd 写入 ISO 到 U 盘（黑名单已覆盖 of=/dev/sd，这里作为兜底）
    (r"\bdd\b\s+if=.*of=", "dd 写入", "dd 写入（高风险）"),
]


# 白名单：正则 + 简短理由
_WHITELIST: list[tuple[str, str]] = [
    (r"apt(?:-get)?\s+install\s+", "安装软件包（apt）"),
    (r"apt(?:-get)?\s+update\s*$", "刷新软件包索引"),
    (r"apt(?:-get)?\s+list\s", "列出软件包"),
    (r"apt(?:-get)?\s+show\s", "查看软件包信息"),
    (r"apt(?:-get)?\s+search\s", "搜索软件包"),
    (r"flatpak\s+install\s+", "安装 Flatpak 应用"),
    (r"flatpak\s+(?:list|search|info)\b", "查询 Flatpak 信息"),
    (r"flatpak\s+update\s+", "更新 Flatpak 应用"),
    (r"flatpak\s+remote-add\s+", "添加 Flatpak 仓库"),
    (r"flatpak\s+remote-ls\s+", "列出 Flatpak 仓库内容"),
    (r"snap\s+install\s+", "安装 Snap 应用"),
    (r"snap\s+(?:list|find|info)\b", "查询 Snap 信息"),
    (r"gsettings\s+(?:set|get)\s+", "读写 GNOME 桌面设置"),
    (r"gsettings\s+(?:list|range|writable|reset-recursively)\s+",
     "查询 GNOME 桌面设置"),
    (r"dconf\s+(?:read|list|dump)\s+", "查询桌面配置"),
    (r"dconf\s+write\s+", "写入桌面配置"),
    (r"fcitx5(?:-\w+)?\b", "输入法操作"),
    (r"ibus(?:-\w+)?\b", "输入法操作"),
    (r"fc-cache\b", "刷新字体缓存"),
    (r"fc-list\b", "列出字体"),
    (r"fc-match\b", "匹配字体"),
    (r"gnome-tweaks\b", "GNOME 调整工具"),
    (r"gnome-extensions\s+(?:list|info|show|enable|disable)\b",
     "管理 GNOME 扩展"),
    (r"systemctl\s+--user\s+", "用户级 systemd 操作"),
    (r"systemctl\s+--user\s+status\s+", "查看用户服务状态"),
    (r"journalctl\s+--user\b", "查看用户日志"),
    (r"\bls\b(?:\s|$)", "列出目录"),
    (r"\bcat\b\s+", "查看文件"),
    (r"\bhead\b\s+", "查看文件头"),
    (r"\btail\b\s+", "查看文件尾"),
    (r"\bgrep\b\s+", "搜索文本"),
    (r"\bfind\b\s+", "查找文件"),
    (r"\bwhich\b\s+", "查找命令路径"),
    (r"\bwhereis\b\s+", "查找命令路径"),
    (r"\bfile\b\s+", "识别文件类型"),
    (r"\bstat\b\s+", "查看文件信息"),
    (r"\bdu\b\s+", "查看目录大小"),
    (r"\bdf\b\s+", "查看磁盘空间"),
    (r"\bps\b\s+", "查看进程"),
    # v0.8.0: 无害输出命令（run_shell 万能工具常用）
    (r"^\s*echo\b\s+", "输出文本"),
    (r"^\s*printf\b\s+", "输出文本"),
    (r"^\s*(?:true|false)\s*$", "无操作命令"),
    (r"\btop\b(?:\s|$)", "查看进程"),
    (r"\bfree\b\s+", "查看内存"),
    (r"\buname\b\s+", "查看系统信息"),
    (r"\bwhoami\b\s*$", "查看当前用户"),
    (r"\bdate\b\s*", "查看时间"),
    (r"\buptime\b\s*$", "查看运行时间"),
    (r"\blscpu\b\s*$", "查看 CPU 信息"),
    (r"\blspci\b\s+", "查看 PCI 设备"),
    (r"\blsusb\b\s*$", "查看 USB 设备"),
    (r"\bip\b\s+(?:addr|link|route)\s+(?:show|list)", "查看网络配置"),
    (r"\bnmcli\b\s+(?:device|connection|general|networking)\s+(?:show|list|status)",
     "查看网络状态"),
    (r"\bdig\b\s+", "DNS 查询"),
    (r"\bnslookup\b\s+", "DNS 查询"),
    (r"\bping\b\s+", "网络连通性测试"),
    (r"\bcurl\b\s+-[IL]", "HTTP HEAD 请求"),
    (r"\bwget\b\s+--spider", "HTTP 探测"),
    (r"\bmkdir\s+-p\s+~/", "在用户目录下创建目录"),
    (r"\btouch\s+~/", "在用户目录下创建文件"),
    (r"\btar\s+-[a-zA-Z]+\s+", "tar 压缩/解压"),
    (r"\bunzip\b\s+", "解压 zip"),
    (r"\b7z\b\s+", "7z 压缩/解压"),
    (r"\bpip3?\s+install\s+", "安装 Python 包"),
    (r"\bpip3?\s+list\b", "列出 Python 包"),
    (r"\bpip3?\s+show\s+", "查看 Python 包信息"),
    (r"\bpip3?\s+search\s+", "搜索 Python 包"),
    (r"\bnpm\s+install\s+", "安装 npm 包（项目内）"),
    (r"\bnpm\s+list\b", "列出 npm 包"),
    (r"\bnode\s+--version\b", "查看 Node 版本"),
    (r"\bpython3?\s+--version\b", "查看 Python 版本"),
    (r"\bpython3?\s+-m\s+pip\b", "pip 模块"),
    (r"\bgit\s+(?:status|log|diff|branch|show|fetch|pull)\b",
     "git 只读操作"),
    (r"\bgsettings\s+set\s+org\.gnome\.desktop\.interface\s+",
     "设置 GNOME 外观"),
    (r"\bgsettings\s+set\s+org\.gnome\.desktop\.background\s+",
     "设置壁纸"),
    (r"\bgsettings\s+set\s+org\.gnome\.shell\s+",
     "设置 GNOME Shell"),
    (r"\bnotify-send\b\s+", "发送桌面通知"),
    (r"\bscreenshot\b", "截图"),
    (r"\bgrim\b\s+", "Wayland 截图"),
    (r"\bslurp\b\s+", "Wayland 区域选择"),
    (r"\bwl-copy\b\s+", "Wayland 剪贴板"),
    (r"\bwl-paste\b\s+", "Wayland 剪贴板"),
    (r"\bxclip\b\s+", "X11 剪贴板"),
    (r"\bxsel\b\s+", "X11 剪贴板"),
    (r"\bbrightnessctl\b\s+", "调整亮度"),
    (r"\bpactl\b\s+", "音量控制"),
    (r"\bamixer\b\s+", "音量控制"),
    (r"\bplayerctl\b\s+", "播放器控制"),
    (r"\bswaymsg\b\s+", "Sway 窗口管理"),
    (r"\bswaylock\b\s+", "锁屏"),
    (r"\bloginctl\s+lock-session\b", "锁屏"),
    (r"\bxdg-open\b\s+", "用默认应用打开"),
    (r"\bxdg-mime\b\s+", "查询默认应用"),
    (r"\bupdate-desktop-database\b", "更新应用菜单缓存"),
    (r"\bgtk-update-icon-cache\b", "更新图标缓存"),
    # 新增白名单：查询类命令
    (r"\btimedatectl\b(?:\s+(?:status|show))?(?:\s|$)", "查看时间/时区状态"),
    (r"\blocale\b(?:\s|$)", "查看语言环境"),
    (r"\blocale\s+-a\b", "列出所有语言环境"),
    (r"\bhostnamectl\b(?:\s|$)", "查看主机信息"),
    (r"\bhostname\b\s*$", "查看主机名"),
    (r"\bsystemctl\s+(?:status|is-active|is-enabled|list-units|list-unit-files|show|cat)\b",
     "查询系统服务"),
    (r"\bsystemctl\s+(?:list-units|list-unit-files)\b", "列出系统服务"),
    (r"\bjournalctl\b", "查看系统日志"),
    (r"\bdmidecode\b\s+-t\s+", "查看硬件信息"),
    (r"\blshw\b", "查看硬件信息"),
    (r"\blscpu\b", "查看 CPU 信息"),
    (r"\blsblk\b", "查看块设备"),
    (r"\blsmod\b", "查看内核模块"),
    (r"\blspci\b", "查看 PCI 设备"),
    (r"\blsusb\b", "查看 USB 设备"),
    (r"\blsnet\b", "查看网络设备"),
    (r"\biwconfig\b(?:\s|$)", "查看无线网络"),
    (r"\biw\b\s+(?:list|dev|wlan0\s+link)", "查看无线网络"),
    (r"\bnmcli\s+(?:device|connection|general|networking|radio)\s+(?:show|list|status)",
     "查看网络状态"),
    (r"\bnmcli\s+connection\s+show\b", "查看网络连接"),
    (r"\bnmcli\s+device\s+(?:status|list|show)\b", "查看网络设备"),
    (r"\bip\s+(?:addr|link|route|neigh)\s+(?:show|list)?", "查看网络配置"),
    (r"\bip\s+-br\s+(?:addr|link|route)", "查看网络配置（简洁）"),
    (r"\bss\b\s+", "查看 socket"),
    (r"\bnetstat\b\s+", "查看网络连接"),
    (r"\bnmap\b\s+", "网络扫描"),
    (r"\btraceroute\b\s+", "路由追踪"),
    (r"\btracepath\b\s+", "路由追踪"),
    (r"\bmtr\b\s+", "网络诊断"),
    (r"\bifconfig\b(?:\s|$)", "查看网络接口"),
    (r"\bairmon-ng\b\s+", "无线网卡监控"),
    (r"\bbluetoothctl\b(?:\s+(?:list|info|devices|show))?(?:\s|$)",
     "查看蓝牙信息"),
    (r"\brfkill\b\s+(?:list|event)", "查看无线设备状态"),
    (r"\bdf\b", "查看磁盘空间"),
    (r"\bdu\b", "查看目录大小"),
    (r"\bdust\b\s+", "查看目录大小"),
    (r"\bncdu\b\s+", "交互式磁盘分析"),
    (r"\bfindmnt\b", "查看挂载点"),
    (r"\bmount\b\s*$", "查看挂载"),
    (r"\bmountpoint\b\s+", "检查挂载点"),
    (r"\bstat\b\s+", "查看文件信息"),
    (r"\bfile\b\s+", "识别文件类型"),
    (r"\bwc\b\s+", "统计文件"),
    (r"\bmd5sum\b\s+", "计算 MD5"),
    (r"\bsha256sum\b\s+", "计算 SHA256"),
    (r"\bbase64\b\s+", "Base64 编解码"),
    (r"\bhexdump\b\s+", "十六进制查看"),
    (r"\bxxd\b\s+", "十六进制查看"),
    (r"\bstrings\b\s+", "提取字符串"),
    (r"\bawk\b\s+", "文本处理"),
    (r"\bsed\b\s+", "文本处理"),
    (r"\bsort\b\s+", "排序"),
    (r"\buniq\b\s+", "去重"),
    (r"\btr\b\s+", "字符替换"),
    (r"\bcut\b\s+", "字段提取"),
    (r"\bpaste\b\s+", "合并文件"),
    (r"\bjoin\b\s+", "连接文件"),
    (r"\bcomm\b\s+", "比较文件"),
    (r"\bdiff\b\s+", "比较文件"),
    (r"\bpatch\b\s+", "应用补丁"),
    (r"\bhead\b\s+", "查看文件头"),
    (r"\btail\b\s+", "查看文件尾"),
    (r"\bless\b\s+", "分页查看"),
    (r"\bmore\b\s+", "分页查看"),
    (r"\bzcat\b\s+", "查看压缩文件"),
    (r"\bzgrep\b\s+", "搜索压缩文件"),
    (r"\bunzip\s+-l\b", "查看 zip 内容"),
    (r"\b7z\s+l\b", "查看 7z 内容"),
    (r"\btar\s+-[a-zA-Z]*t[a-zA-Z]*\s+", "查看 tar 内容"),
    (r"\bprintenv\b", "查看环境变量"),
    (r"\benv\b\s*$", "查看环境变量"),
    (r"\bexport\s+\w+=\S+\s*$", "设置环境变量（当前会话）"),
    # v0.8.7: 补充常用只读诊断命令（LLM 诊断问题时常用，原被分到 unknown 走 confirm 挡路）
    (r"\bdmesg\b(?:\s|$)", "查看内核日志"),
    (r"\bw\b\s*$", "查看登录用户"),
    (r"\bwho\b\s*$", "查看登录用户"),
    (r"\bid\b\s*$", "查看当前用户身份"),
    (r"\bid\b\s+\S+", "查看指定用户身份"),
    (r"\blast\b(?:\s|$)", "查看最近登录记录"),
    (r"\btype\b\s+", "查看命令类型"),
    (r"\balias\b\s*$", "查看命令别名"),
    (r"\bhistory\b(?:\s|$)", "查看 shell 历史"),
    (r"\bdate\b\s*", "查看时间"),
    (r"\bcal\b\s*", "查看日历"),
    (r"\bncal\b\s*", "查看日历"),
    (r"\btime\b\s+", "计时"),
    (r"\barch\b\s*$", "查看 CPU 架构"),
    (r"\bnproc\b\s*$", "查看 CPU 核数"),
    (r"\bsensors\b", "查看温度传感器"),
    (r"\bwatch\b\s+", "周期执行"),
    (r"\btimeout\b\s+", "超时控制"),
    (r"\bnohup\b\s+", "后台运行"),
    (r"\bdisown\b", "脱离 shell"),
    (r"\bjobs\b\s*$", "查看后台任务"),
    (r"\bfg\b\s*", "切换到前台"),
    (r"\bbg\b\s*", "切换到后台"),
    (r"\bpgrep\b\s+", "查找进程"),
    (r"\bpkill\b\s+-f\s+\S+", "按命令名杀进程"),
    (r"\bpidof\b\s+", "查找进程 PID"),
    (r"\bkillall\s+-u\s+\S+\s+-e\b", "按用户杀进程"),
    (r"\bkillall\s+-I\s+", "交互式杀进程"),
    (r"\brenice\b\s+", "调整进程优先级"),
    (r"\bnice\b\s+", "调整进程优先级"),
    (r"\bionice\b\s+", "调整 IO 优先级"),
    (r"\bchrt\b\s+", "调整实时优先级"),
    (r"\btaskset\b\s+", "设置 CPU 亲和性"),
    (r"\biso-info\b", "查看 ISO 信息"),
    (r"\bcrc32\b\s+", "计算 CRC32"),
    (r"\bxxd\b\s+", "十六进制查看"),
    (r"\bcut\b\s+", "字段提取"),
    (r"\bpaste\b\s+", "合并文件"),
    (r"\bjoin\b\s+", "连接文件"),
    (r"\bcolumn\b\s+", "格式化列"),
    (r"\bfold\b\s+", "折叠长行"),
    (r"\bfmt\b\s+", "格式化段落"),
    (r"\bpr\b\s+", "格式化打印"),
    (r"\bnl\b\s+", "编号行"),
    (r"\bseq\b\s+", "生成序列"),
    (r"\bshuf\b\s+", "随机排序"),
    (r"\bsplit\b\s+", "分割文件"),
    (r"\bc split\b\s+", "分割文件"),
    (r"\bcsplit\b\s+", "上下文分割文件"),
    (r"\btac\b\s+", "反向显示"),
    (r"\brev\b\s+", "反转字符"),
    (r"\biconv\b\s+", "编码转换"),
    (r"\benca\b\s+", "检测编码"),
    (r"\bdos2unix\b\s+", "转换换行符"),
    (r"\bunix2dos\b\s+", "转换换行符"),
    (r"\bpdfinfo\b\s+", "查看 PDF 信息"),
    (r"\bpdftotext\b\s+", "PDF 转文本"),
    (r"\bpdftoppm\b\s+", "PDF 转图片"),
    (r"\bpdftk\b\s+", "PDF 工具"),
    (r"\bqpdf\b\s+", "PDF 工具"),
    (r"\bconvert\b\s+", "ImageMagick 转换"),
    (r"\bidentify\b\s+", "ImageMagick 识别"),
    (r"\bmogrify\b\s+", "ImageMagick 批处理"),
    (r"\bmontage\b\s+", "ImageMagick 拼图"),
    (r"\bcomposite\b\s+", "ImageMagick 合成"),
    (r"\bffmpeg\b\s+", "ffmpeg 媒体处理"),
    (r"\bffprobe\b\s+", "查看媒体信息"),
    (r"\bplay\b\s+", "SoX 播放音频"),
    (r"\brec\b\s+", "SoX 录音"),
    (r"\bsox\b\s+", "SoX 音频处理"),
    (r"\bmediainfo\b\s+", "查看媒体信息"),
    (r"\bexiftool\b\s+", "查看 EXIF"),
    (r"\bmkvinfo\b\s+", "查看 MKV 信息"),
    (r"\bmkvextract\b\s+", "提取 MKV 轨道"),
    (r"\bmkvmerge\b\s+", "合并 MKV"),
    (r"\byoutube-dl\b\s+", "下载视频"),
    (r"\byt-dlp\b\s+", "下载视频"),
    (r"\bstreamlink\b\s+", "观看直播"),
    (r"\blibreoffice\b\s+--headless\s+--convert", "Office 转换"),
    (r"\bdu\b\s*-sh\s+~", "查看用户目录大小"),
    (r"\bneofetch\b\s*$", "neofetch 系统信息"),
    (r"\bfastfetch\b\s*$", "fastfetch 系统信息"),
    (r"\bscreenfetch\b\s*$", "screenfetch 系统信息"),
    (r"\binxi\b\s+-[Ffv]", "inxi 系统信息"),
    (r"\bhwinfo\b\s*$", "hwinfo 硬件信息"),
    (r"\bhardinfo\b\s*$", "hardinfo 硬件信息"),
    (r"\bcpuid\b\s*$", "cpuid CPU 信息"),
    (r"\bdmidecode\b\s+-t\s+", "查看硬件信息"),
    (r"\bsmartctl\s+-[aAHi]\b", "查看硬盘 SMART"),
    (r"\bhdparm\s+-[Ii]\b", "查看硬盘信息"),
    (r"\bsgdisk\s+-p\b", "查看 GPT 分区"),
    (r"\bfdisk\s+-l\b", "查看分区表"),
    (r"\bcfdisk\b\s*$", "交互式分区工具"),
    (r"\bparted\s+-l\b", "查看分区"),
    (r"\bblockdev\s+--getsize64\b", "查看块设备大小"),
    (r"\bblkid\b(?:\s|$)", "查看块设备 ID"),
    # v0.8.7: GPU/图形/显示诊断命令（LLM 诊断 GPU/显示问题时常用，原被分到 unknown 走 confirm 挡路）
    # nvidia-smi 任意参数都只读（-q 查询 / -l 周期 / -i 指定 GPU / --query-gpu 查询字段）
    (r"\bnvidia-smi\b(?:\s|$)", "查看 NVIDIA GPU 状态"),
    # glxinfo / vainfo / vulkaninfo 只读查询图形/视频加速信息
    (r"\bglxinfo\b(?:\s|$)", "查看 OpenGL 信息"),
    (r"\bvainfo\b(?:\s|$)", "查看视频加速信息"),
    (r"\bvulkaninfo\b(?:\s|$)", "查看 Vulkan 信息"),
    (r"\bdrm_info\b(?:\s|$)", "查看 DRM 信息"),
    # xrandr 只读查询（裸命令 / --query / --current / --listmonitors / --verbose）
    # 注意：--output XXX --off / --mode / --rate 是修改操作，已走灰名单（L227-228）
    (r"\bxrandr\b(?:\s+(?:--query|--current|--listmonitors|--verbose|--prop|--screen|--q1|--q12))?\s*$",
     "查看屏幕信息"),
    # lscpu / lsblk 支持带参数（-J JSON / -f 文件系统 / -o 自定义列）
    (r"\blscpu\b(?:\s|$)", "查看 CPU 信息"),
    (r"\blsblk\b(?:\s|$)", "查看块设备"),
    (r"\blsmod\b(?:\s|$)", "查看内核模块"),
    # D-Bus 只读查询（gsettings 已在上面，这里补 dbus-send --session 查询）
    (r"\bdbus-send\b.*--print-reply", "D-Bus 查询"),
    # gdbus 只读查询（introspect / call Get 类属性）
    (r"\bgdbus\b.*--introspect", "D-Bus 内省"),
    (r"\bfindfs\b\s+", "按标签/UUID 查找文件系统"),
    (r"\bfsck\b\s+-n\b", "检查文件系统（只读）"),
    (r"\btune2fs\s+-l\b", "查看 ext 文件系统"),
    (r"\bdumpe2fs\b", "查看 ext 文件系统"),
    (r"\bxfs_info\b", "查看 XFS 文件系统"),
    (r"\bbtrfs\s+subvolume\s+list\b", "查看 Btrfs 子卷"),
    (r"\bbtrfs\s+filesystem\s+show\b", "查看 Btrfs 文件系统"),
    (r"\bbtrfs\s+filesystem\s+df\b", "查看 Btrfs 使用"),
    (r"\bmdadm\s+--detail\s+--scan\b", "查看 RAID"),
    (r"\bmdadm\s+--query\b", "查看 RAID"),
    (r"\blvdisplay\b", "查看 LVM"),
    (r"\bvgdisplay\b", "查看 LVM"),
    (r"\bpvdisplay\b", "查看 LVM"),
    (r"\blvs\b\s*$", "查看 LVM"),
    (r"\bvgs\b\s*$", "查看 LVM"),
    (r"\bpvs\b\s*$", "查看 LVM"),
    (r"\bcryptsetup\b\s+(?:status|luksDump)\b", "查看加密卷"),
    (r"\bifstat\b\s+", "查看网络流量"),
    (r"\biftop\b\s+", "查看网络流量"),
    (r"\bhtop\b\s*$", "htop 进程监控"),
    (r"\bbtop\b\s*$", "btop 进程监控"),
    (r"\bcpustat\b\s+", "CPU 统计"),
    (r"\bmemstat\b\s+", "内存统计"),
    (r"\bvmstat\b\s+", "虚拟内存统计"),
    (r"\biostat\b\s+", "IO 统计"),
    (r"\bdstat\b\s+", "系统统计"),
    (r"\bsar\b\s+", "系统活动统计"),
    (r"\bpidstat\b\s+", "进程统计"),
    (r"\bmpstat\b\s+", "CPU 统计"),
    (r"\bnethogs\b\s+", "按进程网络流量"),
    (r"\bprocinfo\b\s+", "查看 /proc 信息"),
    (r"\bstrace\s+-p\s+", "跟踪进程系统调用"),
    (r"\bltrace\s+-p\s+", "跟踪进程库调用"),
    (r"\blsof\b\s+", "查看打开的文件"),
    (r"\bfuser\b\s+", "查看文件使用者"),
    (r"\baplay\s+-l\b", "查看音频设备"),
    (r"\baplay\s+-L\b", "查看音频设备"),
    (r"\bpactl\s+(?:list|info|get-|stat)", "查看 PulseAudio"),
    (r"\bpw-cli\b\s+info\b", "查看 PipeWire"),
    (r"\bpw-cli\b\s+list-objects\b", "查看 PipeWire"),
    (r"\bwpctl\s+status\b", "查看 WirePlumber"),
    (r"\bwpctl\s+inspect\b", "查看 WirePlumber"),
    (r"\bwpctl\s+get-volume\b", "查看音量"),
    (r"\bsolaar\b\s+show\b", "查看罗技设备"),
    (r"\blpstat\b\s+", "查看打印机状态"),
    (r"\blpq\b\s+", "查看打印队列"),
    (r"\blpinfo\b\s+", "查看打印机驱动"),
    (r"\bcupsctl\b\s*$", "查看 CUPS 配置"),
    (r"\blpoptions\b\s*$", "查看打印机选项"),
    (r"\bxinput\b\s+(?:list|state)", "查看输入设备"),
    (r"\bxrandr\s+--listmonitors\b", "查看显示器"),
    (r"\bxrandr\s+--query\b", "查看屏幕"),
    (r"\bwlr-randr\b\s*$", "查看 Wayland 屏幕"),
    (r"\bkscreen-doctor\b\s+-o\b", "查看 KDE 屏幕"),
    (r"\bhyprctl\b\s+monitors\b", "查看 Hyprland 屏幕"),
    (r"\bhyprctl\b\s+clients\b", "查看 Hyprland 窗口"),
    (r"\bhyprctl\b\s+workspaces\b", "查看 Hyprland 工作区"),
    (r"\bswaymsg\b\s+-t\s+get_(?:outputs|inputs|tree|config|workspaces)",
     "查看 Sway 状态"),
    (r"\bi3-msg\b\s+-t\s+get_(?:outputs|inputs|tree|config|workspaces)",
     "查看 i3 状态"),
    (r"\bgrim\b\s+/", "Wayland 截图到文件"),
    (r"\bgnome-screenshot\b\s+-w\s*$", "GNOME 截当前窗口"),
    (r"\bscrot\b\s+/", "X11 截图到文件"),
    (r"\bimport\b\s+/", "ImageMagick 截图"),
    (r"\bspectacle\b\s+/", "KDE 截图"),
    (r"\bflameshot\b\s+full\s+-p\s+/", "flameshot 全屏截图"),
    (r"\bflameshot\b\s+gui\b", "flameshot 交互截图"),
    (r"\bwl-screenrec\b\s+/", "Wayland 录屏"),
    (r"\bobs\b\s+--startrecording", "OBS 录屏"),
    (r"\bsimplescreenrecorder\b", "SSR 录屏"),
    (r"\bbluetoothctl\s+(?:list|info|devices|show)\b",
     "查看蓝牙信息"),
    (r"\bbtmgmt\b\s+--info\b", "查看蓝牙信息"),
    (r"\bhciconfig\b(?:\s|$)", "查看蓝牙适配器"),
    (r"\bhcitool\b\s+(?:dev|scan|inquiry)", "查看蓝牙设备"),
    (r"\brfcomm\b\s*$", "查看蓝牙串口"),
    (r"\bsdptool\b\s+(?:browse|search)", "查看蓝牙服务"),
    (r"\bl2ping\b\s+", "蓝牙 ping"),
    (r"\bgatttool\b\s+-b\s+\S+\s+--interactive\b", "BLE 交互"),
    (r"\bbluetoothctl\s+scan\s+on\b", "扫描蓝牙设备"),
    (r"\bbluetoothctl\s+scan\s+off\b", "停止扫描"),
    (r"\bdbus-send\b\s+--dest=org\.bluez\b", "蓝牙 DBus 查询"),
    (r"\bgdbus\s+call\s+--dest=org\.bluez\b", "蓝牙 DBus 查询"),
    (r"\bnmcli\s+(?:general|networking|radio|connection|device)\s+(?:status|show|list)\b",
     "查看网络状态"),
    (r"\bnmcli\s+connection\s+show\b", "查看网络连接"),
    (r"\bnmcli\s+device\s+status\b", "查看网络设备"),
    (r"\bnmcli\s+device\s+wifi\s+list\b", "扫描 WiFi"),
    (r"\bnmcli\s+device\s+wifi\s+rescan\b", "重新扫描 WiFi"),
    (r"\bnmcli\s+general\s+permissions\b", "查看 NetworkManager 权限"),
    (r"\bnmcli\s+general\s+logging\b", "查看 NetworkManager 日志"),
    (r"\biw\b\s+dev\s+\S+\s+link\b", "查看 WiFi 连接"),
    (r"\biw\b\s+list\b", "查看无线网卡能力"),
    (r"\biwconfig\b\s*$", "查看无线网络"),
    (r"\biwlist\b\s+scan\b", "扫描 WiFi"),
    (r"\bwpa_cli\b\s+(?:status|list|scan_results|ping)\b", "查看 WPA"),
    (r"\bairmon-ng\b\s+start\s+\S+\s*$", "无线网卡监控"),
    (r"\bnetctl\s+list\b", "查看 netctl 配置"),
    (r"\bconnmanctl\s+services\b", "查看 Connman 服务"),
    (r"\bip\s+route\s+show\b", "查看路由表"),
    (r"\bip\s+neigh\s+show\b", "查看 ARP"),
    (r"\bip\s+rule\s+show\b", "查看路由规则"),
    (r"\broute\s+-n\b", "查看路由表"),
    (r"\barp\s+-a\b", "查看 ARP"),
    (r"\bbridge\b\s+link\s+show\b", "查看网桥"),
    (r"\bbridge\b\s+vlan\s+show\b", "查看 VLAN"),
    (r"\bbridge\b\s+fdb\s+show\b", "查看转发表"),
    (r"\bovs-vsctl\b\s+show\b", "查看 Open vSwitch"),
    (r"\bovs-ofctl\b\s+dump-flows\b", "查看 OpenFlow 流表"),
    (r"\bipset\b\s+list\b", "查看 ipset"),
    (r"\bnft\b\s+list\s+ruleset\b", "查看 nftables 规则"),
    (r"\biptables\s+-L\b", "查看 iptables 规则"),
    (r"\bip6tables\s+-L\b", "查看 ip6tables 规则"),
    (r"\bufw\s+status\b", "查看 ufw 状态"),
    (r"\bufw\s+status\s+verbose\b", "查看 ufw 详细状态"),
    (r"\bfirewall-cmd\b\s+--list-all\b", "查看 firewalld"),
    (r"\bfirewall-cmd\b\s+--get-?\w+\b", "查询 firewalld"),
    (r"\bcamera\b\s+--list\b", "查看摄像头"),
    (r"\bv4l2-ctl\b\s+--list-devices\b", "查看视频设备"),
    (r"\bv4l2-ctl\b\s+-d\s+\S+\s+--all\b", "查看摄像头信息"),
    (r"\buvcdynctrl\b\s+-d\s+\S+\s+--list\b", "查看摄像头"),
    (r"\bfswebcam\b\s+--list\b", "查看摄像头"),
    (r"\bcheese\b\s+$", "摄像头测试"),
    (r"\bgphoto2\b\s+--auto-detect\b", "查看相机"),
    (r"\bgphoto2\b\s+--summary\b", "查看相机信息"),
    (r"\bexiftool\b\s+", "查看 EXIF"),
    (r"\bimagemagick\b\s+", "ImageMagick"),
    (r"\bconvert\b\s+", "ImageMagick"),
    (r"\bidentify\b\s+", "ImageMagick"),
    (r"\bfbi\b\s+--list\b", "查看图片"),
    (r"\bfim\b\s+--list\b", "查看图片"),
    (r"\bfbida\b\s+--list\b", "查看图片"),
    (r"\bfeh\s+-l\b", "查看图片列表"),
    (r"\bsxiv\s+-t\b", "缩略图"),
    (r"\bnsxiv\s+-t\b", "缩略图"),
    (r"\bgeeqie\b\s+$", "图片浏览器"),
    (r"\bgpicview\b\s+$", "图片浏览器"),
    (r"\bgthumb\b\s+$", "图片浏览器"),
    (r"\bqimgv\b\s+$", "图片浏览器"),
    (r"\bnomacs\b\s+$", "图片浏览器"),
    (r"\bmirage\b\s+$", "图片浏览器"),
    (r"\bviewnior\b\s+$", "图片浏览器"),
    (r"\bristretto\b\s+$", "图片浏览器"),
    (r"\beog\b\s+$", "GNOME 图片浏览器"),
    (r"\bloupe\b\s+$", "GNOME 图片浏览器"),
    (r"\bgimp-?\d*\s+--version\b", "查看 GIMP 版本"),
    (r"\binkscape\s+--version\b", "查看 Inkscape 版本"),
    (r"\bkrita\s+--version\b", "查看 Krita 版本"),
    (r"\bdarktable\s+--version\b", "查看 Darktable 版本"),
    (r"\brawtherapee\s+--version\b", "查看 RawTherapee 版本"),
    (r"\bblender\s+--version\b", "查看 Blender 版本"),
    (r"\bopenscad\s+--version\b", "查看 OpenSCAD 版本"),
    (r"\bfreecad\s+--version\b", "查看 FreeCAD 版本"),
    (r"\bopenscad\b\s+--version\b", "查看 OpenSCAD 版本"),
    (r"\bsolvespace\b\s+--version\b", "查看 SolveSpace 版本"),
    (r"\bkicad\s+--version\b", "查看 KiCad 版本"),
    (r"\bfritzing\b\s+--version\b", "查看 Fritzing 版本"),
    (r"\blibreoffice\s+--version\b", "查看 LibreOffice 版本"),
    (r"\bonlyoffice\s+--version\b", "查看 OnlyOffice 版本"),
    (r"\bwps\s+--version\b", "查看 WPS 版本"),
    (r"\byoutrack\b\s+--version\b", "查看 YouTrack 版本"),
    (r"\bidea\s+--version\b", "查看 IntelliJ 版本"),
    (r"\bpycharm\s+--version\b", "查看 PyCharm 版本"),
    (r"\bwebstorm\s+--version\b", "查看 WebStorm 版本"),
    (r"\bclion\s+--version\b", "查看 CLion 版本"),
    (r"\bgoland\s+--version\b", "查看 GoLand 版本"),
    (r"\brider\s+--version\b", "查看 Rider 版本"),
    (r"\bphpstorm\s+--version\b", "查看 PhpStorm 版本"),
    (r"\brubymine\s+--version\b", "查看 RubyMine 版本"),
    (r"\brustrover\s+--version\b", "查看 RustRover 版本"),
    (r"\baqua\s+--version\b", "查看 Aqua 版本"),
    (r"\bdataspell\s+--version\b", "查看 DataSpell 版本"),
    (r"\bappcode\s+--version\b", "查看 AppCode 版本"),
    (r"\bcedit\b\s+--version\b", "查看 Cedit 版本"),
    (r"\bfleet\s+--version\b", "查看 Fleet 版本"),
    (r"\btoolbox\s+--version\b", "查看 Toolbox 版本"),
    (r"\bcode\s+--version\b", "查看 VSCode 版本"),
    (r"\bcodium\s+--version\b", "查看 Codium 版本"),
    (r"\bcursor\s+--version\b", "查看 Cursor 版本"),
    (r"\bvscodium\s+--version\b", "查看 VSCodium 版本"),
    (r"\bsubl\s+--version\b", "查看 Sublime 版本"),
    (r"\batom\s+--version\b", "查看 Atom 版本"),
    (r"\bpulsar\s+--version\b", "查看 Pulsar 版本"),
    (r"\bzed\s+--version\b", "查看 Zed 版本"),
    (r"\blapce\s+--version\b", "查看 Lapce 版本"),
    (r"\bhelix\s+--version\b", "查看 Helix 版本"),
    (r"\bneovim\s+--version\b", "查看 Neovim 版本"),
    (r"\bvim\s+--version\b", "查看 Vim 版本"),
    (r"\bemacs\s+--version\b", "查看 Emacs 版本"),
    (r"\bnano\s+--version\b", "查看 Nano 版本"),
    (r"\bmicro\s+--version\b", "查看 Micro 版本"),
    (r"\bjoe\s+--version\b", "查看 Joe 版本"),
    (r"\bjed\s+--version\b", "查看 Jed 版本"),
    (r"\bne\b\s+--version\b", "查看 Ne 版本"),
    (r"\bjstar\s+--version\b", "查看 Jstar 版本"),
    (r"\bpele\s+--version\b", "查看 Pele 版本"),
    # v0.5.0 新增 Skill 的白名单查询命令
    (r"\brsync\b\s+--version\b", "查看 rsync 版本"),
    (r"\brsync\b\s+--dry-run\b", "rsync 模拟运行"),
    (r"\brsync\b\s+-avn\b", "rsync 模拟运行"),
    (r"\bgpg\b\s+--version\b", "查看 gpg 版本"),
    (r"\bgpg\b\s+--list-keys\b", "列出 gpg 公钥"),
    (r"\bgpg\b\s+--list-secret-keys\b", "列出 gpg 私钥"),
    (r"\bgpg\b\s+-[kK]\b", "列出 gpg 密钥"),
    (r"\bwg\b\s+show\b", "查看 WireGuard 状态"),
    (r"\bwg\b\s+--version\b", "查看 WireGuard 版本"),
    (r"\bopenvpn\b\s+--version\b", "查看 OpenVPN 版本"),
    (r"\bssh\b\s+-V\b", "查看 SSH 版本"),
    (r"\bsmbstatus\b", "查看 Samba 状态"),
    (r"\bsmbclient\b\s+-L\b", "查看 Samba 共享"),
    (r"\btestparm\b", "检查 Samba 配置"),
    (r"\bcoredumpctl\b\s+(?:list|info|debug)", "查看核心转储"),
    (r"\biotop\b\s*$", "查看 IO 占用"),
    (r"\biotop\b\s+-bn1\b", "查看 IO 占用"),
    (r"\bclamscan\b\s+--version\b", "查看 ClamAV 版本"),
    (r"\bclamscan\b\s+-r\b(?!.*--remove)", "扫描病毒（只读）"),
    (r"\bclamscan\b\s+--infected\b", "扫描病毒（只读）"),
    (r"\bubuntu-drivers\b\s+(?:list|devices)\b", "查看显卡驱动"),
    (r"\bprime-select\b\s+--query\b", "查询当前显卡"),
    (r"\bsetxkbmap\b\s+-query\b", "查询键盘布局"),
    (r"\blocalectl\b\s+list-x11-keymap", "列出键盘布局"),
    (r"\bcrontab\b\s+-l\b", "查看定时任务"),
    (r"\bpdfunite\b\s+-v\b", "查看 pdfunite 版本"),
    (r"\bpdfunite\b", "合并 PDF"),
    (r"\bpdfseparate\b\s+-v\b", "查看 pdfseparate 版本"),
    (r"\bpdfseparate\b", "拆分 PDF"),
    (r"\bssh-keygen\b\s+-l\b", "查看密钥指纹"),
    (r"\bssh-keygen\b\s+-y\b", "导出公钥"),
    (r"\bssh-keygen\b\s+--help\b", "查看 ssh-keygen 帮助"),
    (r"\bdocker\b\s+(?:ps|images|logs|stats|version|info|inspect|history|port|top|diff)\b",
     "查询 Docker 信息"),
    (r"\bdocker\b\s+container\s+(?:ls|ps)\b", "查询 Docker 容器"),
    (r"\bdocker\b\s+image\s+(?:ls|list|history|inspect)\b",
     "查询 Docker 镜像"),
    (r"\bfree\b\s*-h\b", "查看内存（人类可读）"),
    (r"\bfree\b\s*-m\b", "查看内存（MB）"),
    (r"\bfree\b\s*-g\b", "查看内存（GB）"),
    (r"\btop\b\s+-bn1\b", "查看进程快照"),
    (r"\bps\b\s+aux\b", "查看所有进程"),
    (r"\bps\b\s+--sort\b", "查看进程（排序）"),
    (r"\bmodinfo\b\s+", "查看内核模块信息"),
    (r"\bdpkg\b\s+--list\b", "查看已安装的包"),
    (r"\bdpkg\b\s+--print-architecture\b", "查看架构"),
    (r"\bdpkg\b\s+--status\b", "查看包状态"),
    (r"\bapt\b\s+policy\b", "查看包策略"),
    (r"\bapt\b\s+depends\b", "查看包依赖"),
    (r"\bapt\b\s+rdepends\b", "查看反向依赖"),
    (r"\bapt\b\s+changelog\b", "查看包变更日志"),
    (r"\bapt\b\s+moo\b", "apt 彩蛋"),
    (r"\bsnap\b\s+(?:list|find|info|changes)\b", "查询 Snap 信息"),
    (r"\bflatpak\b\s+(?:list|search|info|remotes)\b", "查询 Flatpak 信息"),
    (r"\bflatpak\b\s+remote-ls\b", "列出 Flatpak 仓库内容"),
    (r"\bsystemd-analyze\b\s+(?:blame|critical-chain|time)\b",
     "分析启动时间"),
    (r"\bsystemd-analyze\b\s*$", "查看启动耗时"),
    (r"\bsystemd-cgtop\b", "查看 cgroup 占用"),
    (r"\bsystemd-cgls\b", "查看 cgroup 树"),
    (r"\bloginctl\b\s+list-sessions\b", "查看登录会话"),
    (r"\bloginctl\b\s+list-users\b", "查看登录用户"),
    (r"\bhostnamectl\b\s+status\b", "查看主机状态"),
    (r"\btimedatectl\b\s+status\b", "查看时间状态"),
    (r"\btimedatectl\b\s+show\b", "查看时间详情"),
    (r"\btimedatectl\b\s+list-timezones\b", "列出时区"),
    (r"\blocalectl\b\s+status\b", "查看语言环境状态"),
    (r"\bgrub-editenv\b\s+list\b", "查看 GRUB 环境变量"),
    (r"\bgrub-probe\b", "探测 GRUB 设备"),
    (r"\bgrub-mkconfig\b\s+--help\b", "查看 grub-mkconfig 帮助"),
]


# 编译正则以提升性能
_BLACKLIST_COMPILED = [(re.compile(p), r) for p, r in _BLACKLIST]
_GREYLIST_COMPILED = [(re.compile(p), r, t) for p, r, t in _GREYLIST]
_WHITELIST_COMPILED = [(re.compile(p), r) for p, r in _WHITELIST]


# 命令分隔符：把复合命令拆成子命令分别评估
_CMD_SEPARATORS = re.compile(r"(?:;|&&|\|\||\|)")


def _split_command(cmd: str) -> list[str]:
    """把复合命令拆成子命令。简单实现，不处理引号内的分隔符。"""
    parts = _CMD_SEPARATORS.split(cmd)
    return [p.strip() for p in parts if p.strip()]


def _classify_single(cmd: str) -> SafetyDecision:
    """对单个子命令做分类。"""
    if not cmd:
        return SafetyDecision(level="unknown", reason="空命令")
    # 先查黑名单
    for pattern, reason in _BLACKLIST_COMPILED:
        m = pattern.search(cmd)
        if m:
            return SafetyDecision(
                level="black",
                rule=pattern.pattern,
                reason=reason,
                human_message=reason,
            )
    # 再查灰名单
    for pattern, reason, template in _GREYLIST_COMPILED:
        m = pattern.search(cmd)
        if m:
            groups = m.groups()
            try:
                human = template.format(*groups) if groups else template
            except (IndexError, KeyError):
                human = template
            return SafetyDecision(
                level="grey",
                rule=pattern.pattern,
                reason=reason,
                human_message=human,
            )
    # 再查白名单
    for pattern, reason in _WHITELIST_COMPILED:
        if pattern.search(cmd):
            return SafetyDecision(
                level="white",
                rule=pattern.pattern,
                reason=reason,
                auto_execute=True,
            )
    return SafetyDecision(level="unknown", reason="未匹配任何规则")


# 级别优先级（数字越大越严）
_LEVEL_PRIORITY: dict[SafetyLevel, int] = {
    "unknown": 0,
    "white": 1,
    "grey": 2,
    "black": 3,
}


def classify(command: str) -> SafetyDecision:
    """对一条完整命令做安全分类。

    复合命令（含 ; | && ||）会被拆分，按"最严子命令"定级。
    未知子命令会被当作灰名单处理（保守策略），但只有当所有子命令都是未知时，
    整条命令才是 unknown。

    特别处理：含分隔符的危险复合模式（curl|bash、fork bomb）必须整体匹配，
    不能拆分后再分类（否则拆分后子命令会丢失上下文）。
    """
    command = (command or "").strip()
    if not command:
        return SafetyDecision(level="unknown", reason="空命令")

    # 整体黑名单检测：在拆分前先匹配一次，捕获含 | & ; 的危险复合模式
    for pattern, reason in _BLACKLIST_COMPILED:
        if pattern.search(command):
            return SafetyDecision(
                level="black",
                rule=pattern.pattern,
                reason=reason,
                human_message=reason,
            )

    # 检查是否有 shell 元字符需要拆分
    sub_cmds = _split_command(command)
    if len(sub_cmds) == 1:
        return _classify_single(sub_cmds[0])

    sub_decisions = [_classify_single(c) for c in sub_cmds]
    worst = max(sub_decisions, key=lambda d: _LEVEL_PRIORITY[d.level])

    # 如果最严的是 unknown，但其中有白名单子命令，整体降为 white
    # 否则保持 unknown（让上层走灰名单确认流程）
    if worst.level == "unknown":
        if any(d.level == "white" for d in sub_decisions):
            worst = SafetyDecision(
                level="white",
                reason=";".join(d.reason for d in sub_decisions),
                auto_execute=True,
            )

    # 合并人类消息
    grey_msgs = [d.human_message for d in sub_decisions if d.level == "grey" and d.human_message]
    black_msgs = [d.human_message for d in sub_decisions if d.level == "black" and d.human_message]

    if black_msgs:
        human = "；".join(dict.fromkeys(black_msgs))
    elif grey_msgs:
        human = "；".join(dict.fromkeys(grey_msgs))
    else:
        human = worst.human_message

    return SafetyDecision(
        level=worst.level,
        rule=worst.rule,
        reason=worst.reason,
        human_message=human,
        auto_execute=worst.auto_execute and worst.level != "grey",
        sub_decisions=sub_decisions,
    )


def describe_for_user(decision: SafetyDecision, command: str | None = None) -> str:
    """生成给用户看的确认信息（不展示原始命令）。

    灰名单确认时用。如果 decision.human_message 为空，回退到 reason。
    """
    if decision.level == "black":
        return f"❌ 拒绝执行：{decision.human_message or decision.reason}"
    if decision.level == "grey":
        return decision.human_message or decision.reason or "需要确认才能执行"
    if decision.level == "white":
        return f"✅ 自动执行：{decision.reason}"
    return "需要确认才能执行"


def is_dangerous(command: str) -> bool:
    """快捷判断：是否命中黑名单。"""
    return classify(command).level == "black"


def parse_args(command: str) -> list[str]:
    """安全解析命令参数（用 shlex）。失败回退到 split。"""
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()
