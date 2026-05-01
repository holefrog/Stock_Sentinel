# Oracle Cloud VM 及域名排障指南

## 1. OCI 实例 SSH 连接超时 (Connection timed out)
**主要原因**：VCN 缺少公网出口网关，或路由表未配置外网连通规则。

**解决步骤**：
1. **创建网关**：进入 VCN -> Internet Gateways -> `Create Internet Gateway`。
2. **配置指路牌**：进入 VCN -> Route Tables -> `Add Route Rules`。
   - Target Type: `Internet Gateway`
   - Destination CIDR Block: `0.0.0.0/0`
   - 选中刚创建的网关并保存。
3. **防火墙放行**：确认 VCN 的 Security Lists 已存在放行 TCP `22` 端口的入站规则。

## 2. 域名 A 记录修改未生效
**主要原因**：DNS 缓存未更新 (TTL 延迟)，或使用了 CDN 代理。

**排查与解决**：
1. **对比测试**：
   - 查本地缓存：`nslookup yourdomain.com`
   - 查权威节点：`nslookup yourdomain.com 8.8.8.8`
2. **处理方案**：
   - 如果 8.8.8.8 已是新 IP：清理本地 DNS 缓存（如 `ipconfig /flushdns`）或等待宽带运营商缓存过期。
   - 如果返回的是非你设置的未知 IP：检查是否开启了 Cloudflare 等 CDN 代理，需在 CDN 后台修改 A 记录。

## 3. Key权限太宽
```
chmod 400 ssh-key-2026-04-30.key
```
