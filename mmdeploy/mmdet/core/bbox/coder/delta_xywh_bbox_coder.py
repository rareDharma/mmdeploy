import numpy as np
import torch

from mmdeploy.core import FUNCTION_REWRITER


@FUNCTION_REWRITER.register_rewriter(
    func_name='mmdet.core.bbox.coder.delta_xywh_bbox_coder.delta2bbox',  # noqa
    backend='default')
def delta2bbox(ctx,
               rois,
               deltas,
               means=(0., 0., 0., 0.),
               stds=(1., 1., 1., 1.),
               max_shape=None,
               wh_ratio_clip=16 / 1000,
               clip_border=True,
               add_ctr_clamp=False,
               ctr_clamp=32):
    means = deltas.new_tensor(means).view(1,
                                          -1).repeat(1,
                                                     deltas.size(-1) // 4)
    stds = deltas.new_tensor(stds).view(1, -1).repeat(1, deltas.size(-1) // 4)
    denorm_deltas = deltas * stds + means
    dx = denorm_deltas[..., 0::4]
    dy = denorm_deltas[..., 1::4]
    dw = denorm_deltas[..., 2::4]
    dh = denorm_deltas[..., 3::4]

    x1, y1 = rois[..., 0], rois[..., 1]
    x2, y2 = rois[..., 2], rois[..., 3]
    # Compute center of each roi
    px = ((x1 + x2) * 0.5).unsqueeze(-1).expand_as(dx)
    py = ((y1 + y2) * 0.5).unsqueeze(-1).expand_as(dy)
    # Compute width/height of each roi
    pw = (x2 - x1).unsqueeze(-1).expand_as(dw)
    ph = (y2 - y1).unsqueeze(-1).expand_as(dh)

    dx_width = pw * dx
    dy_height = ph * dy

    max_ratio = np.abs(np.log(wh_ratio_clip))
    if add_ctr_clamp:
        dx_width = torch.clamp(dx_width, max=ctr_clamp, min=-ctr_clamp)
        dy_height = torch.clamp(dy_height, max=ctr_clamp, min=-ctr_clamp)
        dw = torch.clamp(dw, max=max_ratio)
        dh = torch.clamp(dh, max=max_ratio)
    else:
        dw = dw.clamp(min=-max_ratio, max=max_ratio)
        dh = dh.clamp(min=-max_ratio, max=max_ratio)
    # Use exp(network energy) to enlarge/shrink each roi
    gw = pw * dw.exp()
    gh = ph * dh.exp()
    # Use network energy to shift the center of each roi
    gx = px + dx_width
    gy = py + dy_height
    # Convert center-xy/width/height to top-left, bottom-right
    x1 = gx - gw * 0.5
    y1 = gy - gh * 0.5
    x2 = gx + gw * 0.5
    y2 = gy + gh * 0.5

    if clip_border and max_shape is not None:
        from mmdeploy.mmdet.export import clip_bboxes
        x1, y1, x2, y2 = clip_bboxes(x1, y1, x2, y2, max_shape)

    bboxes = torch.stack([x1, y1, x2, y2], dim=-1).view(deltas.size())
    return bboxes


@FUNCTION_REWRITER.register_rewriter(
    func_name='mmdet.core.bbox.coder.delta_xywh_bbox_coder.delta2bbox',  # noqa
    backend='ncnn')
def delta2bbox_ncnn(ctx,
                    rois,
                    deltas,
                    means=(0., 0., 0., 0.),
                    stds=(1., 1., 1., 1.),
                    max_shape=None,
                    wh_ratio_clip=16 / 1000,
                    clip_border=True,
                    add_ctr_clamp=False,
                    ctr_clamp=32):
    means = deltas.new_tensor(means).view(1, 1,
                                          -1).repeat(1, deltas.size(-2),
                                                     deltas.size(-1) // 4).data
    stds = deltas.new_tensor(stds).view(1, 1,
                                        -1).repeat(1, deltas.size(-2),
                                                   deltas.size(-1) // 4).data
    denorm_deltas = deltas * stds + means
    if denorm_deltas.shape[-1] == 4:
        dx = denorm_deltas[..., 0:1]
        dy = denorm_deltas[..., 1:2]
        dw = denorm_deltas[..., 2:3]
        dh = denorm_deltas[..., 3:4]
    else:
        dx = denorm_deltas[..., 0::4]
        dy = denorm_deltas[..., 1::4]
        dw = denorm_deltas[..., 2::4]
        dh = denorm_deltas[..., 3::4]

    x1, y1 = rois[..., 0:1], rois[..., 1:2]
    x2, y2 = rois[..., 2:3], rois[..., 3:4]

    # Compute center of each roi
    px = (x1 + x2) * 0.5
    py = (y1 + y2) * 0.5
    # Compute width/height of each roi
    pw = x2 - x1
    ph = y2 - y1

    # do not use expand unless necessary
    # since expand is a custom ops
    if px.shape[-1] != 4:
        px = px.expand_as(dx)
    if py.shape[-1] != 4:
        py = py.expand_as(dy)
    if pw.shape[-1] != 4:
        pw = pw.expand_as(dw)
    if px.shape[-1] != 4:
        ph = ph.expand_as(dh)

    dx_width = pw * dx
    dy_height = ph * dy

    max_ratio = np.abs(np.log(wh_ratio_clip))
    if add_ctr_clamp:
        dx_width = torch.clamp(dx_width, max=ctr_clamp, min=-ctr_clamp)
        dy_height = torch.clamp(dy_height, max=ctr_clamp, min=-ctr_clamp)
        dw = torch.clamp(dw, max=max_ratio)
        dh = torch.clamp(dh, max=max_ratio)
    else:
        dw = dw.clamp(min=-max_ratio, max=max_ratio)
        dh = dh.clamp(min=-max_ratio, max=max_ratio)
    # Use exp(network energy) to enlarge/shrink each roi
    gw = pw * dw.exp()
    gh = ph * dh.exp()
    # Use network energy to shift the center of each roi
    gx = px + dx_width
    gy = py + dy_height
    # Convert center-xy/width/height to top-left, bottom-right
    x1 = gx - gw * 0.5
    y1 = gy - gh * 0.5
    x2 = gx + gw * 0.5
    y2 = gy + gh * 0.5

    if clip_border and max_shape is not None:
        from mmdeploy.mmdet.export import clip_bboxes
        x1, y1, x2, y2 = clip_bboxes(x1, y1, x2, y2, max_shape)

    bboxes = torch.stack([x1, y1, x2, y2], dim=-1).view(deltas.size())
    return bboxes