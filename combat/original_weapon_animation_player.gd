extends Node
class_name OriginalWeaponAnimationPlayer

signal sound_event(sound_name: String, resource_path: String)

var _skeleton: Skeleton3D
var _animations: Dictionary = {}
var _sounds: Dictionary = {}
var _bone_lookup: Dictionary = {}
var _current_name := ""
var _current: Dictionary = {}
var _time := 0.0
var _speed := 1.0
var _loop := false
var _playing := false

func setup(rig_data: Dictionary, skeleton: Skeleton3D) -> void:
	_skeleton = skeleton
	_animations = rig_data.get("animations", {})
	_sounds = rig_data.get("sounds", {})
	_bone_lookup.clear()
	if not is_instance_valid(_skeleton):
		return
	for i in range(_skeleton.get_bone_count()):
		_bone_lookup[_skeleton.get_bone_name(i)] = i

func has_clip(animation_name: String) -> bool:
	return _animations.has(animation_name)

func get_duration(animation_name: String) -> float:
	return float(_animations.get(animation_name, {}).get("duration", 0.0))

func get_sound_path(sound_name: String) -> String:
	return String(_sounds.get(sound_name, ""))

func play(animation_name: String, speed: float = 1.0, loop_override: Variant = null) -> bool:
	if not is_instance_valid(_skeleton) or not _animations.has(animation_name):
		return false
	_current_name = animation_name
	_current = _animations[animation_name]
	_time = 0.0
	_speed = maxf(0.01, speed)
	_loop = bool(_current.get("loop", false)) if loop_override == null else bool(loop_override)
	_playing = true
	_apply_pose(0.0)
	_emit_events(-0.0001, 0.0001)
	return true

func stop() -> void:
	_playing = false
	_current = {}
	_current_name = ""
	if is_instance_valid(_skeleton):
		for i in range(_skeleton.get_bone_count()):
			_skeleton.set_bone_pose(i, Transform3D.IDENTITY)

func _process(delta: float) -> void:
	if not _playing or _current.is_empty() or not is_instance_valid(_skeleton):
		return
	var duration := maxf(0.001, float(_current.get("duration", 0.001)))
	var previous := _time
	var next_time := previous + delta * _speed
	if _loop:
		next_time = fposmod(next_time, duration)
		if next_time < previous:
			_emit_events(previous, duration)
			_emit_events(-0.0001, next_time)
		else:
			_emit_events(previous, next_time)
		_time = next_time
	else:
		_time = minf(next_time, duration)
		_emit_events(previous, _time)
	_apply_pose(_time)
	if not _loop and _time >= duration:
		_playing = false
		if _current_name != "Idle" and _animations.has("Idle"):
			call_deferred("play", "Idle", 1.0, true)

func _apply_pose(at_time: float) -> void:
	for i in range(_skeleton.get_bone_count()):
		_skeleton.set_bone_pose(i, Transform3D.IDENTITY)

	var animated: Dictionary = {}
	for curve in _current.get("position_curves", []):
		var bone_name := _curve_bone_name(String(curve.get("path", "")))
		var bone_index := int(_bone_lookup.get(bone_name, -1))
		if bone_index < 0:
			continue
		var pose: Transform3D = animated.get(bone_name, _skeleton.get_bone_rest(bone_index))
		var value := _sample_vector(curve.get("keys", []), at_time)
		pose.origin = value
		animated[bone_name] = pose

	for curve in _current.get("rotation_curves", []):
		var bone_name := _curve_bone_name(String(curve.get("path", "")))
		var bone_index := int(_bone_lookup.get(bone_name, -1))
		if bone_index < 0:
			continue
		var pose: Transform3D = animated.get(bone_name, _skeleton.get_bone_rest(bone_index))
		var value := _sample_quaternion(curve.get("keys", []), at_time)
		var rest_scale := _skeleton.get_bone_rest(bone_index).basis.get_scale()
		pose.basis = Basis(value).scaled(rest_scale)
		animated[bone_name] = pose

	for bone_name in animated:
		var bone_index := int(_bone_lookup[bone_name])
		var rest := _skeleton.get_bone_rest(bone_index)
		var local_animation: Transform3D = animated[bone_name]
		var pose := rest.affine_inverse() * local_animation
		_skeleton.set_bone_pose(bone_index, pose)

func _curve_bone_name(path: String) -> String:
	var parts := path.split("/")
	return String(parts[parts.size() - 1]) if not parts.is_empty() else path

func _sample_vector(keys: Array, at_time: float) -> Vector3:
	if keys.is_empty():
		return Vector3.ZERO
	if at_time <= float(keys[0].get("time", 0.0)):
		return _to_vector3(keys[0].get("value", [0.0, 0.0, 0.0]))
	for i in range(keys.size() - 1):
		var a: Dictionary = keys[i]
		var b: Dictionary = keys[i + 1]
		var ta := float(a.get("time", 0.0))
		var tb := float(b.get("time", ta))
		if at_time <= tb:
			var weight := clampf((at_time - ta) / maxf(0.000001, tb - ta), 0.0, 1.0)
			return _to_vector3(a.get("value", [0.0, 0.0, 0.0])).lerp(_to_vector3(b.get("value", [0.0, 0.0, 0.0])), weight)
	return _to_vector3(keys[keys.size() - 1].get("value", [0.0, 0.0, 0.0]))

func _sample_quaternion(keys: Array, at_time: float) -> Quaternion:
	if keys.is_empty():
		return Quaternion.IDENTITY
	if at_time <= float(keys[0].get("time", 0.0)):
		return _to_quaternion(keys[0].get("value", [0.0, 0.0, 0.0, 1.0]))
	for i in range(keys.size() - 1):
		var a: Dictionary = keys[i]
		var b: Dictionary = keys[i + 1]
		var ta := float(a.get("time", 0.0))
		var tb := float(b.get("time", ta))
		if at_time <= tb:
			var weight := clampf((at_time - ta) / maxf(0.000001, tb - ta), 0.0, 1.0)
			return _to_quaternion(a.get("value", [0.0, 0.0, 0.0, 1.0])).slerp(_to_quaternion(b.get("value", [0.0, 0.0, 0.0, 1.0])), weight).normalized()
	return _to_quaternion(keys[keys.size() - 1].get("value", [0.0, 0.0, 0.0, 1.0]))

func _to_vector3(value: Variant) -> Vector3:
	return Vector3(float(value[0]), float(value[1]), float(value[2]))

func _to_quaternion(value: Variant) -> Quaternion:
	return Quaternion(float(value[0]), float(value[1]), float(value[2]), float(value[3])).normalized()

func _emit_events(from_time: float, to_time: float) -> void:
	if to_time < from_time:
		return
	for event in _current.get("events", []):
		var event_time := float(event.get("time", 0.0))
		if event_time > from_time and event_time <= to_time:
			emit_signal("sound_event", String(event.get("data", "")), String(event.get("sound_path", "")))
