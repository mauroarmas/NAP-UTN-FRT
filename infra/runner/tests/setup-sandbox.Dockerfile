FROM debian:13-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 openssh-server sudo && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_*
