# End-to-End LeRobot Framework for Custom Arms

This repo sets up a LeRobot-based framework for custom robotic arms (leader/follower) using Feetech motors.

## Setup
1. Clone the repo: `git clone https://github.com/FLASH-73/end2end_framework.git`
2. Build Docker: `docker build -t lerobot_custom_arm .`
3. Run container: `docker run --rm -it --device=/dev/ttyUSB0:/dev/ttyUSB0 --privileged lerobot_custom_arm`

## Testing
Run `python tests/test_robot.py` inside the container.