Check with ifconfig what is the wireless interface. Most of the time it's wlp1s0

1.If nmcli is installed then exclude wifi interface from it
sudo nano /etc/NetworkManager/NetworkManager.conf

add:
[keyfile]
unmanaged-devices=interface-name:wlp1s0

restart:
sudo systemctl restart NetworkManager

2.Add this in netplan file. Don't overwrite other settings

network:
  version: 2
  renderer: networkd
  ethernets:
    wlp1s0:
      dhcp4: no
      addresses:
        - 192.168.50.1/24

Then apply settings:
sudo netplan apply

3.Instal hostapd for access point and dnsmasq for dhcp
sudo apt update
sudo apt install hostapd dnsmasq

can install offline:
apt download dnsmasq
apt download dnsmasq-base
apt download hostapd
then move to machine and sudo dpkg -i package_name

sudo systemctl disable hostapd
sudo systemctl disable dnsmasq


4.Edit hostapd config
sudo nano /etc/hostapd/hostapd.conf

Put this in:

interface=wlp1s0
driver=nl80211
ssid=simbox
hw_mode=g
channel=6
ieee80211n=1
wmm_enabled=1
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=imsiimsi
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP

5.In hostapd.conf tell hostapd where the config file is:

sudo nano /etc/default/hostapd

DAEMON_CONF="/etc/hostapd/hostapd.conf"

6.Backup and edit dnsmasq file
sudo cp -p /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
sudo nano /etc/dnsmasq.conf

add this:
interface=wlp1s0
dhcp-range=192.168.50.10,192.168.50.100,12h
bind-dynamic
no-resolv

7.Enable services
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

sudo systemctl start hostapd
sudo systemctl start dnsmasq



#So there won't be conflict with other dns
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved








8.Optional - for future, if want ip forwarding, then:

sudo nano /etc/sysctl.conf

Uncomment this:
net.ipv4.ip_forward=1

And apply:
sudo sysctl -p
