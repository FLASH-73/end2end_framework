# Dockerfile
FROM pytorch/pytorch:2.3.0-cuda11.8-cudnn8-runtime

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    libusb-1.0-0-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install LeRobot and dependencies
RUN pip install lerobot[usb-cameras] feetech-servo-sdk
# Copy your project files
WORKDIR /app
COPY . /app/
# Previous content remains the same, add this line before the ENTRYPOINT or at the end of installations
RUN pip install pyrealsense2
# Install additional dependencies
RUN pip install -r requirements.txt

# Expose USB port for motors
ENV USB_PORT=/dev/ttyUSB0
VOLUME /dev

# Command to run your application
CMD ["bash"]