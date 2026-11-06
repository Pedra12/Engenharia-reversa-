extends CharacterBody3D

var target: Node3D
var combat: Node
var health := 100
var fire_wait := 0.0
var strafe_sign := 1.0
var strafe_wait := 0.0
var visual: MeshInstance3D

func configure(player_target: Node3D, combat_owner: Node, soldier_mesh: Mesh, soldier_material: Material) -> void:
	target = player_target
	combat = combat_owner
	collision_layer = 1
	collision_mask = 3
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.34
	capsule.height = 1.8
	var shape := CollisionShape3D.new()
	shape.shape = capsule
	shape.position.y = 0.9
	add_child(shape)
	visual = MeshInstance3D.new()
	visual.name = "OriginalSoldierMesh"
	visual.mesh = soldier_mesh
	visual.material_override = soldier_material
	visual.rotation_degrees.x = -90.0
	visual.scale = Vector3.ONE * 0.92
	add_child(visual)

func _physics_process(delta: float) -> void:
	if not is_instance_valid(target) or health <= 0:
		return
	fire_wait = maxf(0.0, fire_wait - delta)
	strafe_wait -= delta
	if strafe_wait <= 0.0:
		strafe_sign *= -1.0
		strafe_wait = randf_range(2.0, 4.0)
	var offset := target.global_position - global_position
	offset.y = 0.0
	var distance := offset.length()
	if distance > 0.01:
		look_at(Vector3(target.global_position.x, global_position.y, target.global_position.z), Vector3.UP)
	var direction := Vector3.ZERO
	if distance > 9.0:
		direction = offset.normalized()
	elif distance > 4.0:
		direction = Vector3(-offset.normalized().z, 0.0, offset.normalized().x) * strafe_sign * 0.45
	velocity.x = direction.x * 2.4
	velocity.z = direction.z * 2.4
	if not is_on_floor():
		velocity.y -= 9.8 * delta
	move_and_slide()
	if distance < 24.0 and fire_wait <= 0.0:
		fire_wait = randf_range(1.1, 1.7)
		if is_instance_valid(combat):
			combat.call("bot_shoot", self)

func take_damage(amount: int) -> bool:
	health = maxi(0, health - amount)
	if health == 0:
		if is_instance_valid(combat):
			combat.call("bot_killed", self)
		queue_free()
		return true
	return false
