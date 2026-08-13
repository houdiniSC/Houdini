# openvpn

- Category: VPN client (egress control, geo/ISP bypass)
- Usage: `sudo openvpn --config <profile>.ovpn --auth-user-pass ~/vpn-profiles/auth.txt --daemon --log /tmp/vpn.log`
- Profiles: `~/vpn-profiles/*.ovpn` (auth in `~/vpn-profiles/auth.txt`)
- Notes: verify egress after connect (`curl ifconfig.me`); openvpn needs root
