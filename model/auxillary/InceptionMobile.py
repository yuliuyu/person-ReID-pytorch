import torch.nn as nn
import math
import torch

def conv_bn(inp, oup, stride):
    return nn.Sequential(
        nn.Conv2d(inp, oup, 3, stride, 1, bias=False),
        nn.BatchNorm2d(oup),
        nn.ReLU6(inplace=True)
    )


def conv_1x1_bn(inp, oup):
    return nn.Sequential(
        nn.Conv2d(inp, oup, 1, 1, 0, bias=False),
        nn.BatchNorm2d(oup),
        nn.ReLU6(inplace=True)
    )


class InvertedResidual(nn.Module):
    def __init__(self, inp, oup, stride, expand_ratio=0.5):
        super(InvertedResidual, self).__init__()
        self.stride = stride
        assert stride in [1, 2]

        hidden_dim = round(inp * expand_ratio)
        
        if self.stride == 1 and inp == oup:
            self.use_res_connect = True
        else:
            self.use_res_connect = False
            self.downsample = nn.Sequential(
                nn.Conv2d(inp, oup, 1, self.stride, 0, bias=False),
                nn.BatchNorm2d(oup)
            )

        self.conv1 = nn.Sequential(
            # pw
            nn.Conv2d(inp, hidden_dim, 1, 1, 0, bias=False),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU6(inplace=True)
        )
        self.conv2_1 = nn.Sequential(
            # dw
            nn.Conv2d(hidden_dim, hidden_dim, 3, stride, 1, groups=hidden_dim, bias=False, dilation=1),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU6(inplace=True),
        )
        self.conv2_3 = nn.Sequential(
            # dw
            nn.Conv2d(hidden_dim, hidden_dim, 3, stride, 3, groups=hidden_dim, bias=False, dilation=3),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU6(inplace=True),
        )
        self.conv2_6 = nn.Sequential(
            # dw
            nn.Conv2d(hidden_dim, hidden_dim, 3, stride, 6, groups=hidden_dim, bias=False, dilation=6),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU6(inplace=True),
        )
        self.conv2_9 = nn.Sequential(
            # dw
            nn.Conv2d(hidden_dim, hidden_dim, 3, stride, 9, groups=hidden_dim, bias=False, dilation=9),
            nn.BatchNorm2d(hidden_dim),
            nn.ReLU6(inplace=True),
        )
        self.conv3 = nn.Sequential(
            # pw-linear
            nn.Conv2d(hidden_dim * 4, oup, 1, 1, 0, bias=False),
            nn.BatchNorm2d(oup),
        )

    def forward(self, x):
        x0 = self.conv1(x)
        x1 = self.conv2_1(x0)
        x2 = self.conv2_3(x0)
        x3 = self.conv2_6(x0)
        x4 = self.conv2_9(x0)
        x_out = torch.cat((x1, x2, x3, x4), 1)
        x_out = self.conv3(x_out)
        if self.use_res_connect:
            return x_out + x
        else:
            return self.downsample(x) + x_out

class MobileNetV2(nn.Module):
    def __init__(self, n_class=1000, input_size=224, width_mult=1.):
        super(MobileNetV2, self).__init__()
        block = InvertedResidual
        input_channel = 32
        last_channel = 1280
        
        interverted_residual_setting = [
            # expand_ratio, out_channel(*width_mult), block_num, stride
            [1, 16, 1, 1],
            [6, 24, 2, 2],
            [6, 32, 3, 2],
            [6, 64, 4, 2],
            [6, 96, 3, 1],
            [6, 160, 3, 2],
            [6, 320, 1, 1],
        ]

        # building first layer
        assert input_size % 32 == 0
        input_channel = int(input_channel * width_mult)
        self.last_channel = int(last_channel * width_mult) if width_mult > 1.0 else last_channel
        self.features = [conv_bn(3, input_channel, 2)]
        # building inverted residual blocks
        for t, c, n, s in interverted_residual_setting:
            output_channel = int(c * width_mult)
            for i in range(n):
                if i == 0:
                    self.features.append(block(input_channel, output_channel, s, expand_ratio=t))
                else:
                    self.features.append(block(input_channel, output_channel, 1, expand_ratio=t))
                input_channel = output_channel
        # building last several layers
        self.features.append(conv_1x1_bn(input_channel, self.last_channel))
        # make it nn.Sequential
        self.features = nn.Sequential(*self.features)

        # building classifier
        self.classifier = nn.Sequential(
            nn.Dropout(0.2),
            nn.Linear(self.last_channel, n_class),
        )

        self._initialize_weights()

    def forward(self, x):
        x = self.features(x)
        x = x.mean(3).mean(2)
        x = self.classifier(x)
        return x

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.Linear):
                n = m.weight.size(1)
                m.weight.data.normal_(0, 0.01)
                m.bias.data.zero_()
