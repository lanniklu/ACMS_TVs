#!/usr/bin/env python3
"""
Quick test to verify Onvifer XML generation
This script tests the XML configuration generation without requiring ADB
"""

import uuid
import time

def generate_device_xml(camera_ip: str, username: str, password: str, 
                       name: str, model: str) -> str:
    """Generate ListDevice.xml content for camera configuration"""
    device_uid = str(uuid.uuid4())
    
    xml_content = f"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<listDevice>
  <DeviceInfo>
    <sAddress>{camera_ip}</sAddress>
    <iPort>80</iPort>
    <sUserName>{username}</sUserName>
    <sPassword>{password}</sPassword>
    <sName>{name}</sName>
    <sModel>{model}</sModel>
    <deviceType>ONVIF</deviceType>
    <transportProtocol>HTTP</transportProtocol>
    <uid>{device_uid}</uid>
    <iChannel>1</iChannel>
    <iStream>0</iStream>
    <onvifPort>80</onvifPort>
    <httpPort>80</httpPort>
    <rtspPort>554</rtspPort>
    <rtmpPort>1935</rtmpPort>
    <isOnline>true</isOnline>
    <lastUpdateTime>{int(time.time() * 1000)}</lastUpdateTime>
  </DeviceInfo>
</listDevice>"""
    return xml_content

if __name__ == "__main__":
    # Test with camera IMAM parameters
    xml = generate_device_xml(
        camera_ip="10.1.5.20",
        username="admin",
        password="CAMERA_PASSWORD_REDACTED",
        name="IMAM",
        model="SF-IPDM855ZH-2"
    )
    
    print("Generated Onvifer Configuration:")
    print("=" * 70)
    print(xml)
    print("=" * 70)
    print("\nConfiguration ready for deployment!")
