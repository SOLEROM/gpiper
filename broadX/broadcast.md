# broadcast

Broadcast (1 → all on subnet)

Definition: Packets are sent to every host on the local subnet, whether they want it or not.

Addressing / Subnet
* IPv4 only
* Subnet broadcast address ;     Example: 192.168.1.255 for /24
* Layer-2 limited (never routed)


Transport
* UDP only

Advantages
* Zero configuration
* Useful for discovery
* No receiver setup needed

Disadvantages
* All hosts receive traffic (wasteful)
* Not routable
* Can cause broadcast storms
* Often blocked by OS / switches

