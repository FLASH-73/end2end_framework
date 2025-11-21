#!/usr/bin/env python

# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from lerobot.teleoperators.umbra_leader.config_umbra_leader import UmbraLeaderConfig
from lerobot.teleoperators.umbra_leader import UmbraLeaderRobot

from ..teleoperator import Teleoperator
from .config_bi_umbra_leader import BiUmbraLeaderConfig

logger = logging.getLogger(__name__)

class BiUmbraLeader(Teleoperator):
    """Teleoperator class for BiUmbra Leader arm."""
    config_class = BiUmbraLeaderConfig
    name = "bi_umbra_leader"

    def __init__(self, config: BiUmbraLeaderConfig):
        super().__init__(config)
        self.config = config

        left_arm_config = UmbraLeaderConfig(
            id=f"{config.id}_left" if config.id else None,
            calibration_dir=config.calibration_dir,
            port=config.left_arm_port,
            disable_torque_on_disconnect=config.left_arm_disable_torque_on_disconnect,
            max_relative_target=config.left_arm_max_relative_target,
            use_degrees=config.left_arm_use_degrees,
            cameras={},
        )
        right_arm_config = UmbraLeaderConfig(
            id=f"{config.id}_right" if config.id else None,
            calibration_dir=config.calibration_dir,
            port=config.right_arm_port,
            disable_torque_on_disconnect=config.right_arm_disable_torque_on_disconnect,
            max_relative_target=config.right_arm_max_relative_target,
            use_degrees=config.right_arm_use_degrees,
            cameras={},
        )
        self.left_arm = UmbraLeaderRobot(left_arm_config)
        self.right_arm = UmbraLeaderRobot(right_arm_config)

    @property
    def is_connected(self) -> bool:
        return self.left_arm.is_connected and self.right_arm.is_connected

    def connect(self) -> None:
        self.left_arm.connect()
        self.right_arm.connect()

    def get_action(self) -> dict[str, float]:
        # Get actions from both arms
        left_action = self.left_arm.get_action()
        right_action = self.right_arm.get_action()

        # Prefix keys to distinguish left vs right
        # (e.g., "base.pos" becomes "left_base.pos")
        out_action = {}
        for key, val in left_action.items():
            out_action[f"left_{key}"] = val
        for key, val in right_action.items():
            out_action[f"right_{key}"] = val
            
        return out_action

    def disconnect(self):
        self.left_arm.disconnect()
        self.right_arm.disconnect()