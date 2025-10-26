from lerobot.common.robot_devices.robots.manipulator import ManipulatorRobot

# Load the robot from your config
robot = ManipulatorRobot.from_yaml("lerobot/configs/robot/leader.yaml")

try:
    # Connect to the arm (enables torque, etc.)
    robot.connect()
    print("Connected to leader arm successfully.")

    # Read current observations (joint positions in rad)
    obs = robot.get_observation()
    print("Current joint positions:")
    for joint, pos in obs.items():
        if ".pos" in joint:  # Filter to positions
            print(f"{joint}: {pos:.4f} rad")

except Exception as e:
    print(f"Error during test: {str(e)}")

finally:
    # Always disconnect to release resources
    if robot.is_connected:
        robot.disconnect()
    print("Disconnected from leader arm.")