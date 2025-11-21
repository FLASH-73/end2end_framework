import torch

print("PyTorch version:", torch.__version__)
print(torch.cuda.is_available())  # Should return True
print(torch.version.cuda)  # Should show 12.8
import torchvision  # Should import without error