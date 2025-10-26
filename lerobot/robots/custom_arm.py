import math
from typing import Dict, Optional, Any
import torch
from lerobot.common.robot_devices.actuators.feetech import FeetechActuator
from lerobot.common.robot_devices.robots.manipulator import ManipulatorRobot, Arm
from lerobot.common.robot_devices.actuators.bus import Bus
from lerobot.common.robot_devices.cameras.v4l2_camera import V4l2Camera  # Example camera, adjust if needed

class DualFeetechActuator(FeetechActuator):
    """Custom actuator for dual-servos controlling one joint (opposed/mirrored)."""
    def __init__(
        self,
        name: str,
        leader_id: int,
        follower_id: int,
        bus: Bus,
        model: str = "sts3215",
        calibration: Optional[Dict[str, Any]] = None,
        scale: float = 2048 / math.pi,  # Default ticks per rad (approx for STS3215)
        offset: float = 2048,  # Default offset
        **kwargs,
    ):
        super().__init__(name, leader_id, bus, model, **kwargs)
        self.leader = FeetechActuator(f"{name}_leader", leader_id, bus, model, calibration=calibration, **kwargs)
        self.follower = FeetechActuator(
            f"{name}_follower",
            follower_id,
            bus,
            model,
            calibration=calibration,
            **kwargs
        )
        # Set follower to mirrored: orientation -1 equivalent via offset and scale
        self.follower.offset = 4095 - offset
        self.follower.orientation = -1
        self.follower.scale = scale  # Same scale
        self.scale = scale
        self.offset = offset
        self.orientation = 1  # For leader

    def connect(self):
        self.leader.connect()
        self.follower.connect()

    def disconnect(self):
        self.leader.disconnect()
        self.follower.disconnect()

    def read(self, key: str):
        leader_val = self.leader.read(key)
        follower_val = self.follower.read(key)
        if key == "position":
            # Average the positions in user units (rad or m)
            return (leader_val + follower_val) / 2
        return leader_val  # For other keys, return leader's (assuming sync)

    def write(self, key: str, value):
        # Write same value to both; internal to_device handles mirroring
        self.leader.write(key, value)
        self.follower.write(key, value)

    def calibrate(self, *args, **kwargs):
        # Calibrate both
        self.leader.calibrate(*args, **kwargs)
        self.follower.calibrate(*args, **kwargs)

class LinearGripperActuator(FeetechActuator):
    """Custom actuator for linear gripper (dist in meters to ticks)."""
    def __init__(
        self,
        name: str,
        motor_id: int,
        bus: Bus,
        model: str = "sts3215",
        min_dist: float = 0.0,
        max_dist: float = 0.024,
        min_ticks: int = 2903,
        max_ticks: int = 1518,
        **kwargs,
    ):
        super().__init__(name, motor_id, bus, model, **kwargs)
        self.min_dist = min_dist
        self.max_dist = max_dist
        self.min_ticks = min_ticks
        self.max_ticks = max_ticks
        self.scale = (max_ticks - min_ticks) / (max_dist - min_dist)  # Negative
        self.offset = min_ticks  # At dist=0
        self.orientation = 1  # Scale handles direction

    def to_device(self, user_value: float) -> int:
        # user_value is dist in m
        return int(self.offset + user_value * self.scale)

    def from_device(self, device_value: int) -> float:
        return (device_value - self.offset) / self.scale

class CustomFeetechArm(ManipulatorRobot):
    """Custom robot class for Feetech-based arms (leader or follower)."""
    def __init__(self, config: Dict, **kwargs):
        super().__init__(config, **kwargs)

    @classmethod
    def from_config(cls, config_path: str):
        # Load config and initialize
        # You can add custom logic here if needed
        return cls(config_path)

# Example usage in code (not needed in file)
# robot = CustomFeetechArm("lerobot/configs/robot/follower.yaml")
# robot.connect()
# robot.calibrate()  # Or use CLI: lerobot calibrate lerobot/configs/robot/follower.yaml