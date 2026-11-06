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
var shoot_animation_timer := 0.0
var current_locomotion := ""

func configure(player_target: CharacterBody3D, combat_owner: Node, original_rig_loader: OriginalRigLoader, original_weapon_mesh: Mesh, original_weapon_material: Material) -> void:
	target = player_target
	combat = combat_owner
	rig_loader = original_rig_loader
	collision_layer = 1
	collision_mask = 3
	add_to_group("combat_enemy")

	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.27
	capsule.height = 1.45
	var collision := CollisionShape3D.new()
	collision.shape = capsule
	collision.position.y = 0.73
	add_child(collision)

	var rig := rig_loader.create_rig(self, "sk_char_sold_male_01", true)
	if rig.is_empty():
		push_error("Original soldier rig could not be loaded for bot.")
		return
	visual_root = rig["root"]
	skeleton = rig["skeleton"]
	anim_player = ANIMATION_PLAYER_SCRIPT.new()
	add_child(anim_player)
	anim_player.setup(skeleton)
	if anim_player.has_clip("Rifle_Idle_gun_down"):
		anim_player.play("Rifle_Idle_gun_down")
	else:
		anim_player.play("Idle")
	weapon_mount = Node3D.new()
	weapon_mount.name = "WeaponMount"
	var socket_name := "socket_hand_right"
	if skeleton.find_bone(socket_name) < 0:
		socket_name = "hand_r"
	var attachment := rig_loader.create_bone_attachment(skeleton, socket_name, "OriginalWeaponSocket")
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
		var facing := atan2(-to_target.x, -to_target.z)
		rotation.y = lerp_angle(rotation.y, facing, delta * 5.0)
	var direction := Vector3.ZERO
	if distance > 9.0:
		direction = to_target.normalized()
	elif distance < 4.5:
		direction = -to_target.normalized()
	else:
		direction = to_target.normalized() * 0.18
		direction += Vector3(sin(strafe_phase), 0.0, cos(strafe_phase)) * 0.48
	velocity.x = direction.x * speed
	velocity.z = direction.z * speed
	velocity.y -= 18.0 * delta
	move_and_slide()
	if anim_player and shoot_animation_timer <= 0.0:
		var locomotion := "front_run" if direction.length() > 0.7 else ("front_walk" if direction.length() > 0.25 else "Rifle_Idle_gun_down")
		if not anim_player.has_clip(locomotion):
			locomotion = "Idle"
		if locomotion != current_locomotion:
			current_locomotion = locomotion
			anim_player.play(locomotion, 0.16, 1.0)
	if distance < 24.0 and shoot_cooldown <= 0.0 and is_instance_valid(combat):
		shoot_cooldown = 1.15
		shoot_animation_timer = 0.32
		current_locomotion = ""
		if anim_player and anim_player.has_clip("Fire"):
			anim_player.play("Fire", 0.06, 1.0, false)
		combat.call("bot_shoot", self)

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
