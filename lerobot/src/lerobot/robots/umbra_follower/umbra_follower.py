from dataclasses import dataclass, field
from lerobot.cameras.realsense.configuration_realsense import RealSenseCameraConfig
from lerobot.cameras.realsense.camera_realsense import RealSenseCamera
from lerobot.cameras.configs import ColorMode, Cv2Rotation
from lerobot.cameras import CameraConfig
from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.robots import RobotConfig
from lerobot.cameras import make_cameras_from_configs
from lerobot.motors import Motor, MotorNormMode, MotorCalibration
from functools import cached_property
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
import logging
from lerobot.motors.feetech import FeetechMotorsBus
from lerobot.robots import Robot
import time
from typing import Any
from lerobot.motors.feetech import (
    FeetechMotorsBus,
    OperatingMode,
)
from ..utils import ensure_safe_goal_position
from .config_umbra_follower import UmbraFollowerConfig

logger = logging.getLogger(__name__)


class UmbraFollowerRobot(Robot):
    """Robot class for Umbra Follower arm."""
    config_class = UmbraFollowerConfig
    name = "umbra_follower"

  
    def __init__(self, config: UmbraFollowerConfig):
        super().__init__(config)
        self.config = config
        if self.config.arm_side not in ["left", "right"]:
             raise ValueError(f"arm_side must be 'left' or 'right', got {self.config.arm_side}")
        norm_mode_body = MotorNormMode.DEGREES if config.use_degrees else MotorNormMode.RANGE_M100_100
        dual_joints = ["link1", "link2"]
        single_joints = ["base", "link3", "link4", "link5"]
        follower_motors = {
            f"{joint}_follower": Motor(id_val, "sts3215", norm_mode_body)
            for joint, id_val in zip(dual_joints, [3, 5])
        }
        leader_motors = {
            joint: Motor(id_val, "sts3215", norm_mode_body)
            for joint, id_val in zip(dual_joints, [2, 4])
        }
        single_motors = {
            joint: Motor(id_val, "sts3215", norm_mode_body)
            for joint, id_val in zip(single_joints, [1, 6, 7, 8])
        }
        self.bus = FeetechMotorsBus(
            port=self.config.port,
            motors={
                **single_motors,
                **leader_motors,
                "gripper": Motor(9, "sts3215", MotorNormMode.RANGE_0_100),
                **follower_motors,
            },
            calibration=self.calibration,
        )
        self.dual_joints = dual_joints
        self.cameras = make_cameras_from_configs(config.cameras)

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {f"{motor}.pos": float for motor in self.bus.motors if not motor.endswith("_follower")}
                                        
    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }
    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        cam_ft = {
        cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }
        for cam in self.cameras:
            if hasattr(self.config.cameras[cam], 'use_depth') and self.config.cameras[cam].use_depth:
                cam_ft[f"{cam}_depth"] = (self.config.cameras[cam].height, self.config.cameras[cam].width, 1)
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return self._motors_ft

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return self.bus.is_connected and all(cam.is_connected for cam in self.cameras.values())

    def connect(self, calibrate: bool = True) -> None:
        """
        We assume that at connection time, arm is in a rest position,
        and torque can be safely disabled to run calibration.
        """
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")
        logger.info(f"Current motors keys: {list(self.bus.motors.keys())}")
        logger.info(f"Calibration keys: {list(self.calibration.keys()) if self.calibration else 'None'}")
        self.bus.connect()
        if not self.is_calibrated and calibrate:
            logger.info(
                "Mismatch between calibration values in the motor and the calibration file or no calibration file found"
            )
            self.calibrate()

        for cam in self.cameras.values():
            cam.connect()

        self.configure()
        logger.info(f"{self} connected.")
        self.bus.enable_torque()
      

    @property
    def is_calibrated(self) -> bool:
        return self.bus.is_calibrated

    def calibrate(self) -> None:
        if self.calibration:
            # Calibration file exists, ask user whether to use it or run new calibration
            user_input = input(
                f"Press ENTER to use provided calibration file associated with the id {self.id}, or type 'c' and press ENTER to run calibration: "
            )
            if user_input.strip().lower() != "c":
                logger.info(f"Writing calibration file associated with the id {self.id} to the motors")
                self.bus.write_calibration(self.calibration)
                return

        logger.info(f"\nRunning calibration of {self}")
        self.bus.disable_torque()
        for motor in self.bus.motors:
            self.bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)

        input(f"Move {self} to the middle of its range of motion and press ENTER....")
        homing_offsets = self.bus.set_half_turn_homings()

        # Exclude gripper from range recording as it has its own calibration
        print(
            "Move all joints (including gripper) sequentially through their "
            "entire ranges of motion.\nRecording positions. Press ENTER to stop..."
        )
        range_mins, range_maxes = self.bus.record_ranges_of_motion()

        self.calibration = {}
        for motor, m in self.bus.motors.items():
            self.calibration[motor] = MotorCalibration(
                id=m.id,
                drive_mode=0,
                homing_offset=homing_offsets[motor],
                range_min=range_mins[motor],
                range_max=range_maxes[motor],
            )

        self.bus.write_calibration(self.calibration)
        self._save_calibration()
        print("Calibration saved to", self.calibration_fpath)
        self.bus.enable_torque()

    def configure(self) -> None:
        with self.bus.torque_disabled():
            self.bus.configure_motors()
            for motor in self.bus.motors:
                self.bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)
                # Set P_Coefficient to lower value to avoid shakiness (Default is 32)
                self.bus.write("P_Coefficient", motor, 16)
                # Set I_Coefficient and D_Coefficient to default value 0 and 32
                self.bus.write("I_Coefficient", motor, 0)
                self.bus.write("D_Coefficient", motor, 32)

                if motor == "gripper":
                    self.bus.write("Max_Torque_Limit", motor, 500)  # 50% of max torque to avoid burnout
                    self.bus.write("Protection_Current", motor, 250)  # 50% of max current to avoid burnout
                    self.bus.write("Overload_Torque", motor, 25)  # 25% torque when overloaded

    def setup_motors(self) -> None:
        for motor in reversed(self.bus.motors):
            input(f"Connect the controller board to the '{motor}' motor only and press enter.")
            self.bus.setup_motor(motor)
            print(f"'{motor}' motor id set to {self.bus.motors[motor].id}")

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        # Read arm position
        start = time.perf_counter()
        obs_dict = self.bus.sync_read("Present_Position")
        obs_dict = {f"{motor}.pos": val for motor, val in obs_dict.items()}
        #print("Follower:raw_obs", obs_dict)
        # Average positions for dual joints
        '''
        for joint in self.dual_joints:
            obs_dict[f"{joint}.pos"] = (obs_dict[f"{joint}.pos"] - obs_dict[f"{joint}_follower.pos"]) / 2
            del obs_dict[f"{joint}_follower.pos"]
            '''
        #print("Follower:obs", obs_dict)  # for debugging
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read state: {dt_ms:.1f}ms")

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            obs_dict[cam_key] = cam.async_read()
            '''if hasattr(cam.config, 'use_depth') and cam.config.use_depth:
                obs_dict[f"{cam_key}_depth"] = cam.async_read_depth()'''
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict
    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """Command arm to move to a target joint configuration.

        The relative action magnitude may be clipped depending on the configuration parameter
        `max_relative_target`. In this case, the action sent differs from original action.
        Thus, this function always returns the action actually sent.

        Raises:
            RobotDeviceNotConnectedError: if robot is not connected.

        Returns:
            the action sent to the motors, potentially clipped.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        goal_pos = {key.removesuffix(".pos"): val for key, val in action.items() if key.endswith(".pos")}
        #print("Follower:goal_pos", goal_pos)  # for debugging

        # Always read present positions to compute deltas for dual joints and handle capping if enabled.
        present_pos = self.bus.sync_read("Present_Position")

        # Cap goal position when too far away from present position.
        # /!\ Slower fps expected due to reading from the follower.
        if self.config.max_relative_target is not None:
            goal_present_pos = {key: (g_pos, present_pos[key]) for key, g_pos in goal_pos.items()}
            goal_pos = ensure_safe_goal_position(goal_present_pos, self.config.max_relative_target)

        # Set mirrored goals for follower motors in dual joints using deltas to handle offsets.
        
        for joint in self.dual_joints:
            if joint in goal_pos:
                delta = goal_pos[joint] - present_pos[joint]
                goal_pos[f"{joint}_follower"] = present_pos[f"{joint}_follower"] - delta

        # ### CHANGE: ARM-SPECIFIC CONVERSIONS
        if self.config.arm_side == "left":
            # Existing logic for LEFT arm
            if "gripper" in goal_pos:
                goal_pos["gripper"] = 100 - goal_pos["gripper"]
            if "link4" in goal_pos:
                goal_pos["link4"] = -goal_pos["link4"]
            if "link2_follower" in goal_pos:
                goal_pos["link2_follower"] = -goal_pos["link2_follower"]
            if "link2" in goal_pos:
                goal_pos["link2"] = -goal_pos["link2"]
        
        elif self.config.arm_side == "right":
            if "link2_follower" in goal_pos:
                goal_pos["link2_follower"] = -goal_pos["link2_follower"]
            if "link2" in goal_pos:
                goal_pos["link2"] = -goal_pos["link2"]
            if "link1" in goal_pos:
                goal_pos["link1"] = -goal_pos["link1"]
            if "link1_follower" in goal_pos:
                goal_pos["link1_follower"] = -goal_pos["link1_follower"]
            if "link4" in goal_pos:
                goal_pos["link4"] = -goal_pos["link4"]
            # New logic for RIGHT arm (Example - Adjust these to match physical reality)
            # Usually symmetric arms mirror specific joints (like base or shoulder)
            #if "gripper" in goal_pos:
            #    goal_pos["gripper"] = 100 - goal_pos["gripper"] 
            
            # Example: Maybe right arm link4 needs to be positive?
            # if "link4" in goal_pos:
            #     goal_pos["link4"] = goal_pos["link4"] 
            
            # Example: Maybe Link1 on right arm is not inverted?
            # if "link1" in goal_pos:
            #    goal_pos["link1"] = goal_pos["link1"]
        # Default speed value (0-1023; 300 is a safe starting point based on your GUI default.
        # 0 often means "maximum speed" in Feetech protocols—test what works for your servos.
        # Higher values = slower speed in some configs; consult STS3215 manual for units.
        default_speed = 500  # Adjust based on testing (e.g., 0 for max speed, or 200-500 for controlled movement)

        # Set moving speed for all motors being commanded (same keys as goal_pos)
        speed_goals = {motor: default_speed for motor in goal_pos}
        self.bus.sync_write("Goal_Velocity", speed_goals)  # Correct register name for Feetech STS series

        # Send goal position to the arm
        self.bus.sync_write("Goal_Position", goal_pos)
        #print("follower: sent goals", goal_pos)  # for debugging
        return {f"{motor}.pos": val for motor, val in goal_pos.items() if motor in self.bus.motors and not motor.endswith("_follower")}
    def disconnect(self):
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        self.bus.disconnect(self.config.disable_torque_on_disconnect)
        for cam in self.cameras.values():
            cam.disconnect()

        logger.info(f"{self} disconnected.")