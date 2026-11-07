extends CharacterBody3D

const ANIMATION_PLAYER_SCRIPT = preload("res://combat/original_animation_player.gd")

var target: CharacterBody3D
var combat: Node
var rig_loader: OriginalRigLoader
var health := 100.0
var speed := 2.8
var shoot_cooldown := 0.0
var strafe_phase := 0.0
var skeleton: Skeleton3D
var visual_root: Node3D
var weapon_mount: Node3D
var weapon_visual: MeshInstance3D
var dead := false
var anim_player: OriginalAnimationPlayer
var navigation_agent: NavigationAgent3D
var shoot_animation_timer := 0.0
var current_locomotion := ""

func configure(player_target: CharacterBody3D, combat_owner: Node, original_rig_loader: OriginalRigLoader, original_weapon_mesh: Mesh, original_weapon_material: Material) -> void:
	target = player_target
	combat = combat_owner
	rig_loader = original_rig_loader
	collision_layer = 4 # layer 3: bots
	collision_mask = 3 # world (1) + player (2)
	add_to_group("combat_enemy")

	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.27
	capsule.height = 1.45
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	collision.position.y = 0.73
	add_child(collision)

	navigation_agent = NavigationAgent3D.new()
	navigation_agent.name = "OriginalForestNavigationAgent"
	navigation_agent.navigation_layers = 1
	navigation_agent.radius = 0.4
	navigation_agent.height = 1.8
	navigation_agent.path_desired_distance = 0.4
	navigation_agent.target_desired_distance = 1.25
	navigation_agent.path_max_distance = 60.0
	add_child(navigation_agent)

	var rig := rig_loader.create_rig(self, "sk_char_sold_male_01", false)
	if rig.is_empty():
		push_error("Original soldier rig could not be loaded for bot.")
		return
	visual_root = rig["root"]
	skeleton = rig["skeleton"]
	anim_player = ANIMATION_PLAYER_SCRIPT.new()
	add_child(anim_player)
	anim_player.setup(skeleton)
	if anim_player.has_clip("Rifle_Idle_gun_down"):
		anim_player.play("Rifle_Idle_gun_down", 0.14, 1.0, true)
	else:
		anim_player.play("Idle")
	weapon_mount = Node3D.new()
	weapon_mount.name = "WeaponMount"
	var socket_name := "socket_hand_right"
	if skeleton.find_bone(socket_name) < 0:
		socket_name = "hand_r"
	var attachment := rig_loader.create_bone_attachment(skeleton, socket_name, "OriginalWeaponSocket")
	# Exact local transform recovered from sharedassets0.assets:
	# socket_hand_right is parented to hand_r in the original soldier hierarchy.
	# Apply the same X reflection and quaternion conversion used by the rig importer.
	attachment.position = Vector3(-0.11462914, 0.14902945, 0.07855457)
	attachment.quaternion = Quaternion(0.01588862, -0.75679088, -0.62115097, 0.20294526).normalized()
	attachment.add_child(weapon_mount)
	if original_weapon_mesh:
		weapon_visual = MeshInstance3D.new()
		weapon_visual.mesh = original_weapon_mesh
		weapon_visual.material_override = original_weapon_material
		weapon_mount.add_child(weapon_visual)

func _physics_process(delta: float) -> void:
	if dead or not is_instance_valid(target):
		return
	shoot_cooldown = maxf(0.0, shoot_cooldown - delta)
	shoot_animation_timer = maxf(0.0, shoot_animation_timer - delta)
	strafe_phase += delta * 1.8
	var to_target := target.global_position - global_position
	to_target.y = 0.0
	var distance := to_target.length()
	if distance > 0.01:
		var facing := atan2(-to_target.x, -to_target.z) # Convert target direction to Godot's -Z model-forward convention.
		rotation.y = lerp_angle(rotation.y, facing, delta * 5.0)
	var direct_direction := to_target.normalized() if distance > 0.01 else Vector3.ZERO
	var movement_direction := direct_direction
	if navigation_agent and is_instance_valid(navigation_agent):
		if navigation_agent.target_position.distance_to(target.global_position) > 0.5:
			navigation_agent.target_position = target.global_position
		if not navigation_agent.is_navigation_finished():
			var next_path_position := navigation_agent.get_next_path_position()
			var path_direction := next_path_position - global_position
			path_direction.y = 0.0
			if path_direction.length() > 0.15:
				movement_direction = path_direction.normalized()
	var direction := Vector3.ZERO
	if distance > 9.0:
		direction = movement_direction
	elif distance < 4.5:
		direction = -movement_direction
	else:
		direction = movement_direction * 0.18
		direction += Vector3(sin(strafe_phase), 0.0, cos(strafe_phase)) * 0.48
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	velocity.y -= 18.0 * delta
	move_and_slide()
	if anim_player and shoot_animation_timer <= 0.0:
		var locomotion := "Rifle_Idle_gun_down"
		if direction.length() > 0.25:
			var move_direction := direction.normalized()
			var forward_alignment := move_direction.dot(direct_direction)
			var lateral_alignment := move_direction.dot(global_transform.basis.x)
			if forward_alignment < -0.45:
				locomotion = "back_run" if direction.length() > 0.7 else "back_cwalk"
			elif absf(lateral_alignment) > 0.45:
				if lateral_alignment > 0.0:
					locomotion = "right_run" if direction.length() > 0.7 else "right_walk"
				else:
					locomotion = "left_run" if direction.length() > 0.7 else "left_walk"
			else:
				locomotion = "front_run" if direction.length() > 0.7 else "front_walk"
		if not anim_player.has_clip(locomotion):
			locomotion = "front_run" if direction.length() > 0.7 else ("front_walk" if direction.length() > 0.25 else "Idle")
		if not anim_player.has_clip(locomotion):
			locomotion = "Idle"
		if locomotion != current_locomotion:
			current_locomotion = locomotion
			anim_player.play(locomotion, 0.16, 1.0, true)
	if distance < 24.0 and shoot_cooldown <= 0.0 and is_instance_valid(combat) and _has_clear_shot():
		shoot_cooldown = 1.15
		shoot_animation_timer = 0.32
		current_locomotion = ""
		if anim_player and anim_player.has_clip("Fire"):
			anim_player.play("Fire", 0.06, 1.0, false)
		combat.call("bot_shoot", self)

func _has_clear_shot() -> bool:
	if not is_instance_valid(target):
		return false
	var from := global_position + Vector3.UP * 1.35
	var to := target.global_position + Vector3.UP * 1.1
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.collision_mask = 3
	query.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return not hit.is_empty() and hit.collider == target

func take_damage(amount: float, headshot: bool = false) -> bool:
	if dead:
		return false
	health -= amount * (1.7 if headshot else 1.0)
	if health <= 0.0:
		dead = true
		velocity = Vector3.ZERO
		collision_layer = 0
		collision_mask = 0
		set_physics_process(false)
		if anim_player:
			if anim_player.has_clip("Death"):
				anim_player.play("Death", 0.04, 1.0, false)
			elif anim_player.has_clip("Hit Reaction"):
				anim_player.play("Hit Reaction", 0.04, 1.0, false)
		if is_instance_valid(combat):
			combat.call("bot_killed", self)
		return true
	return false
