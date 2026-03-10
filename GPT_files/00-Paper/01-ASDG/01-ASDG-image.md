下面我直接给你一个**改好、可直接生成 Ubuntu 24.04（noble）镜像**的脚本版本，并顺手保留了原本的 Debian 支持，只是多了一层“Debian / Ubuntu 自动判断”。

你可以：

* 直接把原来的 `tools/create-image.sh` 替换成下面这份
* 默认就是 **Ubuntu 24.04 (noble)**
* 如需 Debian 仍然可以 `-d bullseye` / `-d bookworm` 使用

---

## 使用方法（Ubuntu 24.04 镜像）

```bash
cd syzkaller/tools
chmod +x create-image.sh

# 默认就用 noble（Ubuntu 24.04）
./create-image.sh

# 或者显式指定：
./create-image.sh -d noble
```

生成的镜像文件叫：`noble.img`，rootfs 目录叫 `noble/`，SSH key 在当前目录 `noble.id_rsa`。

---

## 修改后的脚本（支持 Ubuntu 24.04）

> 直接整段复制覆盖原来的 `create-image.sh` 即可。

```bash
#!/usr/bin/env bash
# Copyright 2016 syzkaller project authors.
# All rights reserved.
# Use of this source code is governed by Apache 2 LICENSE
# that can be found in the LICENSE file.
#
# create-image.sh 创建一个用于 syzkaller 的最小 Linux 镜像。
# 原版是 Debian-only，这里做了修改：
#   - 默认发行版改为 Ubuntu 24.04 (noble)
#   - 自动根据 RELEASE 判断是 Debian 还是 Ubuntu
#   - Ubuntu 使用 Ubuntu 官方镜像、组件 main,restricted,universe,multiverse
#   - 在 Ubuntu 情况下去掉 firmware-atheros、debian-ports-archive-keyring

set -eux

# 在镜像里预装的基础包
PREINSTALL_PKGS=openssh-server,curl,tar,gcc,libc6-dev,time,strace,sudo,less,psmisc,selinux-utils,policycoreutils,checkpolicy,selinux-policy-default,firmware-atheros,debian-ports-archive-keyring

# 如果外部没有设置 ADD_PACKAGE，就用默认
if [ -z "${ADD_PACKAGE+x}" ]; then
    ADD_PACKAGE="make,sysbench,git,vim,tmux,usbutils,tcpdump"
fi

# 可通过参数修改的变量
ARCH=$(uname -m)
RELEASE=noble          # 默认改成 Ubuntu 24.04 noble
FEATURE=minimal        # minimal / full
SEEK=2047              # 2047 -> 2048MB 镜像
PERF=false

display_help() {
    echo "Usage: $0 [option...]"
    echo
    echo "  -a, --arch          Set architecture (e.g. x86_64, aarch64)"
    echo "  -d, --distribution  Set distribution codename (Debian or Ubuntu):"
    echo "                      e.g. bullseye, bookworm, sid, focal, jammy, noble"
    echo "  -f, --feature       minimal | full (full 会加上 ADD_PACKAGE)"
    echo "  -s, --seek          Image size (MB), default 2048 (2G)"
    echo "  -p, --add-perf      Add perf support (need env \$KERNEL)"
    echo "  -h, --help          Show this help"
}

# 解析参数
while true; do
    if [ $# -eq 0 ]; then
        break
    fi
    case "$1" in
        -h|--help)
            display_help
            exit 0
            ;;
        -a|--arch)
            ARCH=$2
            shift 2
            ;;
        -d|--distribution)
            RELEASE=$2
            shift 2
            ;;
        -f|--feature)
            FEATURE=$2
            shift 2
            ;;
        -s|--seek)
            SEEK=$(($2 - 1))
            shift 2
            ;;
        -p|--add-perf)
            PERF=true
            shift 1
            ;;
        -*)
            echo "Error: Unknown option: $1" >&2
            exit 1
            ;;
        *)
            break
            ;;
    esac
done

# QEMU 架构名 -> Debian/Ubuntu 架构名
case "$ARCH" in
    ppc64le) DEBARCH=ppc64el ;;
    aarch64) DEBARCH=arm64 ;;
    arm)     DEBARCH=armel ;;
    x86_64)  DEBARCH=amd64 ;;
    *)       DEBARCH=$ARCH ;;
esac

# 是否是外部架构（需要 qemu-*-static）
FOREIGN=false
if [ "$ARCH" != "$(uname -m)" ]; then
    # i386 在 x86_64 上可以原生跑，不算 foreign
    if [ "$ARCH" != "i386" ] || [ "$(uname -m)" != "x86_64" ]; then
        FOREIGN=true
    fi
fi

if [ "$FOREIGN" = "true" ]; then
    if ! which qemu-"$ARCH"-static >/dev/null 2>&1; then
        echo "Please install qemu static binary for architecture $ARCH (package 'qemu-user-static')"
        exit 1
    fi
    if [ ! -r /proc/sys/fs/binfmt_misc/qemu-"$ARCH" ]; then
        echo "binfmt entry /proc/sys/fs/binfmt_misc/qemu-$ARCH does not exist"
        exit 1
    fi
fi

# perf 模式需要 KERNEL 环境变量
if [ "$PERF" = "true" ] && [ -z "${KERNEL+x}" ]; then
    echo "Please set KERNEL environment variable when PERF is enabled"
    exit 1
fi

# full 功能会多装一些工具
if [ "$FEATURE" = "full" ]; then
    PREINSTALL_PKGS="$PREINSTALL_PKGS","$ADD_PACKAGE"
fi

DIR=$RELEASE
sudo rm -rf "$DIR"
sudo mkdir -p "$DIR"
sudo chmod 0755 "$DIR"

# -------- 关键改动：根据 RELEASE 判断 Debian 还是 Ubuntu --------

# 能识别的 Ubuntu 代号
UBUNTU_RELEASES="bionic focal jammy noble"

DISTRO="debian"
for r in $UBUNTU_RELEASES; do
    if [ "$RELEASE" = "$r" ]; then
        DISTRO="ubuntu"
        break
    fi
done

# 选择组件和镜像
if [ "$DISTRO" = "ubuntu" ]; then
    # Ubuntu 组件 & 镜像
    COMPONENTS="main,restricted,universe,multiverse"
    MIRROR=${MIRROR:-http://archive.ubuntu.com/ubuntu}
    # Ubuntu 没有 firmware-atheros / debian-ports-archive-keyring，去掉
    PREINSTALL_PKGS=${PREINSTALL_PKGS//,firmware-atheros/}
    PREINSTALL_PKGS=${PREINSTALL_PKGS//,debian-ports-archive-keyring/}
else
    # Debian 组件 & 镜像（保持原逻辑）
    COMPONENTS="main,contrib,non-free,non-free-firmware"
    MIRROR=${MIRROR:-http://deb.debian.org/debian}
fi

# 1. debootstrap stage
DEBOOTSTRAP_PARAMS="--arch=$DEBARCH --include=$PREINSTALL_PKGS --components=$COMPONENTS"

# foreign 架构需要 --foreign
if [ "$FOREIGN" = "true" ]; then
    DEBOOTSTRAP_PARAMS="--foreign $DEBOOTSTRAP_PARAMS"
fi

RET=0

if [ "$DISTRO" = "ubuntu" ]; then
    # 对 Ubuntu：显式指定镜像 + 为了兼容性关闭 GPG 校验（也可以改成安装 ubuntu-keyring 后去掉 no-check-gpg）
    sudo --preserve-env=http_proxy,https_proxy,ftp_proxy,no_proxy \
        debootstrap --no-check-gpg $DEBOOTSTRAP_PARAMS "$RELEASE" "$DIR" "$MIRROR" || RET=$?
else
    # Debian 的情况，保留原有逻辑，包括 EoL fallback
    # riscv64 走 debian-ports
    if [ "$DEBARCH" = "riscv64" ]; then
        DEBOOTSTRAP_PARAMS="--keyring /usr/share/keyrings/debian-ports-archive-keyring.gpg --exclude firmware-atheros $DEBOOTSTRAP_PARAMS $RELEASE $DIR http://deb.debian.org/debian-ports"
        sudo --preserve-env=http_proxy,https_proxy,ftp_proxy,no_proxy debootstrap $DEBOOTSTRAP_PARAMS || RET=$?
    else
        DEBOOTSTRAP_PARAMS="$DEBOOTSTRAP_PARAMS $RELEASE $DIR $MIRROR"
        sudo --preserve-env=http_proxy,https_proxy,ftp_proxy,no_proxy debootstrap $DEBOOTSTRAP_PARAMS || RET=$?
        # 如果是 EoL 版本，尝试 archive 备份仓库
        if [ $RET != 0 ]; then
            DEBOOTSTRAP_PARAMS="--keyring /usr/share/keyrings/debian-archive-removed-keys.gpg $DEBOOTSTRAP_PARAMS https://archive.debian.org/debian-archive/debian/"
            sudo --preserve-env=http_proxy,https_proxy,ftp_proxy,no_proxy debootstrap $DEBOOTSTRAP_PARAMS || true
        fi
    fi
fi

# 2. debootstrap second stage：只有 foreign 架构需要
if [ "$FOREIGN" = "true" ]; then
    sudo cp "$(which qemu-"$ARCH"-static)" "$DIR/$(which qemu-"$ARCH"-static)"
    sudo chroot "$DIR" /bin/bash -c "/debootstrap/debootstrap --second-stage"
fi

# 基本配置：root 无密码登录、串口、网络、fstab、hostname、ssh key 等
sudo sed -i '/^root/ { s/:x:/::/ }' "$DIR/etc/passwd"

echo 'T0:23:respawn:/sbin/getty -L ttyS0 115200 vt100' | sudo tee -a "$DIR/etc/inittab" || true

printf '\nauto eth0\niface eth0 inet dhcp\n' | sudo tee -a "$DIR/etc/network/interfaces"

echo '/dev/root / ext4 defaults 0 0'                 | sudo tee -a "$DIR/etc/fstab"
echo 'debugfs /sys/kernel/debug debugfs defaults 0 0' | sudo tee -a "$DIR/etc/fstab"
echo 'securityfs /sys/kernel/security securityfs defaults 0 0' | sudo tee -a "$DIR/etc/fstab"
echo 'configfs /sys/kernel/config/ configfs defaults 0 0' | sudo tee -a "$DIR/etc/fstab"
echo 'binfmt_misc /proc/sys/fs/binfmt_misc binfmt_misc defaults 0 0' | sudo tee -a "$DIR/etc/fstab"

echo -en "127.0.0.1\tlocalhost\n" | sudo tee "$DIR/etc/hosts"
echo "nameserver 8.8.8.8"          | sudo tee -a "$DIR/etc/resolv.conf"
echo "syzkaller"                   | sudo tee "$DIR/etc/hostname"

ssh-keygen -f "$RELEASE.id_rsa" -t rsa -N ''
sudo mkdir -p "$DIR/root/.ssh/"
cat "$RELEASE.id_rsa.pub" | sudo tee "$DIR/root/.ssh/authorized_keys"

# perf 支持（保持原逻辑）
if [ "$PERF" = "true" ]; then
    cp -r "$KERNEL" "$DIR/tmp/"
    BASENAME=$(basename "$KERNEL")
    sudo chroot "$DIR" /bin/bash -c "apt-get update; apt-get install -y flex bison python-dev libelf-dev libunwind8-dev libaudit-dev libslang2-dev libperl-dev binutils-dev liblzma-dev libnuma-dev"
    sudo chroot "$DIR" /bin/bash -c "apt-get install -y make pkg-config systemtap-sdt-dev libssl-dev libdw-dev libpfm4-dev libtraceevent-dev"
    sudo chroot "$DIR" /bin/bash -c "apt-get install -y python3-setuptools python3-nitime"
    sudo chroot "$DIR" /bin/bash -c "cd /tmp/$BASENAME/tools/perf/; make"
    sudo chroot "$DIR" /bin/bash -c "cp /tmp/$BASENAME/tools/perf/perf /usr/bin/"
    rm -rf "$DIR/tmp/$BASENAME"
fi

# 自定义 udev 规则（原样保留）
echo 'ATTR{name}=="vim2m", SYMLINK+="vim2m"' | sudo tee -a "$DIR/etc/udev/rules.d/50-udev-default.rules"

# 构建磁盘镜像
dd if=/dev/zero of="$RELEASE.img" bs=1M seek="$SEEK" count=1
sudo mkfs.ext4 -F "$RELEASE.img"

sudo mkdir -p "/mnt/$DIR"
sudo mount -o loop "$RELEASE.img" "/mnt/$DIR"
sudo cp -a "$DIR/." "/mnt/$DIR/."
sudo umount "/mnt/$DIR"
```

---

## 关键改动点总结（方便你 Review）

1. **默认发行版改为 Ubuntu 24.04：**

```bash
RELEASE=noble
```

2. **增加 Ubuntu / Debian 判别逻辑：**

```bash
UBUNTU_RELEASES="bionic focal jammy noble"
# DISTRO=ubuntu or debian
```

3. **Ubuntu 使用自己的组件 + 镜像：**

```bash
COMPONENTS="main,restricted,universe,multiverse"
MIRROR=http://archive.ubuntu.com/ubuntu
```

4. **Ubuntu 情况下去掉不存在的包：**

```bash
PREINSTALL_PKGS=${PREINSTALL_PKGS//,firmware-atheros/}
PREINSTALL_PKGS=${PREINSTALL_PKGS//,debian-ports-archive-keyring/}
```

5. **debootstrap 调用对 Ubuntu 显式带 mirror，并用 `--no-check-gpg` 以避免 keyring 问题：**

```bash
debootstrap --no-check-gpg $DEBOOTSTRAP_PARAMS "$RELEASE" "$DIR" "$MIRROR"
```

---

如果你愿意下一步，我还能帮你写一个 **配套的 QEMU 启动脚本**，直接用你之前编译好的内核（BZImage + initrd + 这个 noble.img）一键启动，方便做 syzkaller fuzz。
