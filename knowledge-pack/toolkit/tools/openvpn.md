# openvpn

- Category: VPN client (egress control, geo/ISP bypass)
- Usage: `sudo openvpn --config <profile>.ovpn --auth-user-pass /tmp/openvpn-hermes.auth --daemon --log /tmp/vpn.log`
- Profiles: `~/vpn-profiles/*.ovpn` or `~/vpn-profiles/<provider>/*.ovpn` (multi-provider, recursive)
- Auth: key registry `~/.hermes/toolkit/keys/vpn_user.key` + `vpn_pass.key`
  (default) or `vpn_<provider>_user.key` / `vpn_<provider>_pass.key` (per
  provider) — auth.txt is NOT used
- Notes: verify egress after connect (`curl ifconfig.me`); openvpn needs root;
  profiles + keys added later via Settings are discovered by toolkit-scan
