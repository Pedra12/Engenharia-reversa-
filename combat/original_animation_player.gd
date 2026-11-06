extends Node
class_name OriginalAnimationPlayer

const DATA_PATH := "res://assets/combat_source/original_animations.json"

var skeleton: Skeleton3D
var _clips: Dictionary = {}
var _aliases: Dictionary = {}
var _current: Dictionary = {}
var _current_name := ""
var _time := 0.0
var _speed := 1.0
var _loop := true
var _blend_duration := 0.14
var _blend_elapsed := 0.0
var _blend_from: Dictionary = {}

func setup(target_skeleton: Skeleton3D) -> void:
	skeleton = target_skeleton
	_load_data()

func _load_data() -> void:
	if not _clips.is_empty():
		return
	if not FileAccess.file_exists(DATA_PATH):
		push_error("Original Unity animation database missing: " + DATA_PATH)
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Original Unity animation database is invalid.")
		return
	_aliases = parsed.get("aliases", {})
	for clip in parsed.get("clips", []):
		_clips[String(clip.get("key", clip.get("name", "")))] = clip

func has_clip(clip_name: String) -> bool:
	_load_data()
	var key := String(_aliases.get(clip_name, clip_name))
	return _clips.has(key)

func play(clip_name: String, blend_duration: float = 0.14, speed: float = 1.0, loop_override: Variant = null) -> void:
	_load_data()
	if not is_instance_valid(skeleton):
		return
	var key := String(_aliases.get(clip_name, clip_name))
	if not _clips.has(key):
		return
	if key == _current_name and not _current.is_empty():
		_speed = speed
		return
	_blend_from.clear()
	for i in range(skeleton.get_bone_count()):
		_blend_from[i] = skeleton.get_bone_pose_rotation(i)
	_current = _clips[key]
	_current_name = key
	_time = 0.0
	_speed = speed
	_loop = bool(_current.get("loop", true)) if loop_override == null else bool(loop_override)
	_blend_duration = maxf(0.0, blend_duration)
	_blend_elapsed = 0.0

func stop(reset_pose: bool = true) -> void:
	_current.clear()
	_current_name = ""
	_time = 0.0
	if reset_pose and is_instance_valid(skeleton):
		for i in range(skeleton.get_bone_count()):
			skeleton.set_bone_pose_rotation(i, Quaternion.IDENTITY)

func get_current_animation() -> String:
	return _current_name

func _process(delta: float) -> void:
	if _current.is_empty() or not is_instance_valid(skeleton):
		return
	var frames: Array = _current.get("frames", [])
	if frames.is_empty():
		return
	var duration := maxf(0.001, float(_current.get("duration", 0.001)))
	var fps := maxf(1.0, float(_current.get("fps", 30.0)))
	_time += delta * _speed
	if _loop:
		_time = fposmod(_time, duration)
	else:
		_time = minf(_time, duration)
	var frame_position := clampf((_time / duration) * float(frames.size() - 1), 0.0, float(frames.size() - 1))
	var frame_a := int(floor(frame_position))
	var frame_b := mini(frame_a + 1, frames.size() - 1)
	var alpha := frame_position - float(frame_a)
	var a: Array = frames[frame_a]
	var b: Array = frames[frame_b]
	var b_map: Dictionary = {}
	for item in b:
		b_map[int(item[0])] = item
	var targets: Dictionary = {}
	for item in a:
		var bone_index := int(item[0])
		if bone_index < 0 or bone_index >= skeleton.get_bone_count():
			continue
		var qa := Quaternion(float(item[1]), float(item[2]), float(item[3]), float(item[4]))
		var qb := qa
		if b_map.has(bone_index):
			var other: Array = b_map[bone_index]
			qb = Quaternion(float(other[1]), float(other[2]), float(other[3]), float(other[4]))
		targets[bone_index] = qa.slerp(qb, alpha).normalized()
	var blend_alpha := 1.0
	if _blend_duration > 0.0 and _blend_elapsed < _blend_duration:
		_blend_elapsed = minf(_blend_duration, _blend_elapsed + delta)
		blend_alpha = _blend_elapsed / _blend_duration
	for bone_index in targets:
		var target_q: Quaternion = targets[bone_index]
		if blend_alpha < 1.0 and _blend_from.has(bone_index):
			var from_q: Quaternion = _blend_from[bone_index]
			target_q = from_q.slerp(target_q, blend_alpha).normalized()
		skeleton.set_bone_pose_rotation(int(bone_index), target_q)
