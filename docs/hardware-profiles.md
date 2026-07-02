# Hardware Profiles

Hardware profiles record capacity and compatibility for model/backend decisions.

## Initial Target Class

- Headless Ubuntu Server.
- Large system RAM.
- Many CPU cores.
- Multiple NVIDIA GPUs with large VRAM.
- Small root disk.
- Dedicated large data disk for `/data`.

## Fields To Record

- Hostname and OS.
- CPU model and core/thread count.
- System RAM.
- Root disk identity.
- Data disk identity.
- GPU model, count, driver version, and VRAM.
- Docker and NVIDIA Container Toolkit versions after installation.
