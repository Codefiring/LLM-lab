在 **WSL2** 里验证获取的 **Windows 主机 IP 是否正确**，可以用下面几种可靠的方法。通常 `/etc/resolv.conf` 里的 `nameserver` 就是 Windows 主机地址，但最好验证一下。

---

# 1️⃣ 查看 WSL 获取的 Windows IP（最常用）

```bash
cat /etc/resolv.conf
```

示例：

```
nameserver 172.29.112.1
```

这个 **172.29.112.1** 就是 Windows 主机 IP。

也可以直接提取：

```bash
grep nameserver /etc/resolv.conf | awk '{print $2}'
```

---

# 2️⃣ Ping 测试（最简单）

假设得到：

```
172.29.112.1
```

测试：

```bash
ping 172.29.112.1
```

如果正常：

```
64 bytes from 172.29.112.1: icmp_seq=1 ttl=128
```

说明 **WSL 能访问 Windows 主机**。

---

# 3️⃣ 测试代理端口（最关键）

如果你的代理在 **Windows 7890 端口**：

```bash
curl -v http://172.29.112.1:7890
```

正常会返回：

```
HTTP/1.1 400 Bad Request
```

说明 **端口是通的**。

---

# 4️⃣ 测试真实代理

```bash
export http_proxy=http://172.29.112.1:7890
export https_proxy=http://172.29.112.1:7890

curl https://www.google.com
```

如果成功返回 HTML：

说明代理完全正常。

---

# 5️⃣ 从 Windows 侧验证（最准确）

Windows PowerShell：

```powershell
ipconfig
```

找到：

```
vEthernet (WSL)
```

会看到类似：

```
IPv4 Address : 172.29.112.1
```

这就是 **WSL 的 Windows 网关地址**。

---

# 6️⃣ 使用 route 查看网关（另一种方式）

在 WSL：

```bash
ip route
```

输出：

```
default via 172.29.112.1 dev eth0
```

这个 `default via` 的 IP **也是 Windows 主机地址**。

---

# 7️⃣ 最可靠的一行命令

推荐用这个：

```bash
ip route | grep default | awk '{print $3}'
```

输出：

```
172.29.112.1
```

---

# 📌 推荐最终代理写法（最稳定）

写入 `.bashrc`：

```bash
export hostip=$(ip route | grep default | awk '{print $3}')

export http_proxy="http://$hostip:7890"
export https_proxy="http://$hostip:7890"
export all_proxy="socks5://$hostip:7891"
```

这样 **WSL 重启 IP 变化也不怕**。

---

💡 **补充一个很多人不知道的检查技巧**

如果代理是 **Clash / v2ray**：

```bash
curl ipinfo.io
```

返回：

```
{
  "ip": "代理IP",
  "country": "US"
}
```

说明 **WSL代理成功走 Windows**。

---

如果你愿意，我可以再给你一个 **WSL2 代理终极方案**：

可以实现：

* **WSL 自动继承 Windows 代理**
* **无需 export**
* **支持 Docker / pip / git / apt**
* **重启 WSL 不丢失**

很多 **AI / vLLM / Kubernetes / Docker 开发环境都用这个方案**。
