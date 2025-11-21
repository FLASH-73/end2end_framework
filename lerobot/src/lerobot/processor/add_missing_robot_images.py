# lerobot/src/lerobot/processor/add_missing_robot_images.py

from dataclasses import dataclass, field
from typing import Any, Dict

import torch

from lerobot.configs.types import FeatureType, PipelineFeatureType, PolicyFeature
from lerobot.processor import ObservationProcessorStep, ProcessorStepRegistry


@dataclass
@ProcessorStepRegistry.register("add_missing_robot_images_processor")
class AddMissingRobotImagesProcessorStep(ObservationProcessorStep):
    """Adds missing image observations to robot observations with filled tensors (e.g., -1 for padding).
    
    Use this for inference/recording when the robot has fewer cameras than the policy expects.
    Operates on RobotObservation dict (non-batched, with 'images': dict[str, torch.Tensor]).
    """
    missing_cameras: list[str]  # e.g., ["camera3", "empty_camera_0"]
    shapes: dict[str, tuple[int, ...]]  # e.g., {"camera3": (3, 256, 256), "empty_camera_0": (3, 480, 640)}
    fill_value: float = -1.0  # Matches SmolVLA padding
    duplicate_from: dict[str, str] | None = field(default_factory=dict)  # Optional: e.g., {"camera3": "camera2"}

    def observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        new_images = observation["images"].copy()
        device = observation["state"].device
        dtype = torch.float32

        for cam in self.missing_cameras:
            if cam not in new_images:
                if cam in self.duplicate_from:
                    src_cam = self.duplicate_from[cam]
                    if src_cam in new_images:
                        new_images[cam] = new_images[src_cam].clone()
                        continue
                # Fallback to filled tensor
                shape = self.shapes[cam]
                new_images[cam] = torch.full(shape, self.fill_value, dtype=dtype, device=device)

        new_observation = observation.copy()
        new_observation["images"] = new_images
        return new_observation

    def get_config(self) -> Dict[str, Any]:
        return {
            "missing_cameras": self.missing_cameras,
            "shapes": {k: list(v) for k, v in self.shapes.items()},
            "fill_value": self.fill_value,
            "duplicate_from": self.duplicate_from,
        }

    def state_dict(self) -> Dict[str, torch.Tensor]:
        return {}

    def load_state_dict(self, state: Dict[str, torch.Tensor]) -> None:
        pass

    def reset(self):
        pass

    def transform_features(self, features: dict[PipelineFeatureType, dict[str, PolicyFeature]]) -> dict[PipelineFeatureType, dict[str, PolicyFeature]]:
        print("Transform features called. Current observation keys before adding:", sorted(features.get("observation", {}).keys()))
        obs_features = features.get("observation", {})
        for cam in self.missing_cameras:
            key = f"images.{cam}"
            print("Trying to add key:", key)
            if key not in obs_features:
                obs_features[key] = PolicyFeature(type=FeatureType.VISUAL, shape=self.shapes[cam])
                print("Added key:", key)
            else:
                print("Key already exists, skipping:", key)
        features["observation"] = obs_features
        print("Observation keys after adding:", sorted(features.get("observation", {}).keys()))
        return features