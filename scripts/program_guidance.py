"""Opt-in LingBot reward-gradient hook; explicit VLS-inspired adapter, not native VLS.
No simulator, language edits, parameter updates or model-generated Python execution.
"""
from contextlib import contextmanager

@contextmanager
def velocity_guidance(model, target, indices, scale, ledger):
    import torch
    original = model.predict_velocity
    def wrapped(state, masks, cache, sample, timestep):
        velocity = original(state, masks, cache, sample, timestep)
        if scale == 0:
            ledger.append({"scale": 0.0, "applied": False})
            return velocity
        with torch.enable_grad():
            x = sample.detach().float().requires_grad_(True)
            goal = target.to(x.device, x.dtype)
            reward = -((x[..., indices] - goal[..., indices]) ** 2).mean()
            grad = torch.autograd.grad(reward, x)[0]
            norm = grad.norm()
            grad = grad / (norm + 1e-8)
        assert torch.isfinite(grad).all()
        ledger.append({"scale": scale, "applied": True, "reward": float(reward.detach()),
                       "gradient_norm": float(norm.detach()), "timestep": float(timestep[0])})
        # Native Euler dt is negative: subtracting ascent gradient increases reward.
        return velocity - scale * grad.to(velocity.dtype)
    model.predict_velocity = wrapped
    try:
        yield
    finally:
        model.predict_velocity = original
