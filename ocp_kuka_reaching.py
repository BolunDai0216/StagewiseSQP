'''
Example script : Crocoddyl OCP with KUKA arm 
static target reaching task
'''

import crocoddyl
import numpy as np
import pinocchio as pin
np.set_printoptions(precision=4, linewidth=180)
import ocp_utils
from gnms import GNMS
from gnms_cpp import GNMSCPP
from constraintmodel import FullConstraintModel, EndEffConstraintModel, NoConstraint

from clqr import CLQR
from cilqr import CILQR

# # # # # # # # # # # # #
### LOAD ROBOT MODEL  ###
# # # # # # # # # # # # #

# # Load robot model directly from URDF & mesh files
# from pinocchio.robot_wrapper import RobotWrapper
# urdf_path = '/home/skleff/robot_properties_kuka/urdf/iiwa.urdf'
# mesh_path = '/home/skleff/robot_properties_kuka'
# robot = RobotWrapper.BuildFromURDF(urdf_path, mesh_path) 

# Or use robot_properties_kuka 
from robot_properties_kuka.config import IiwaConfig
robot = IiwaConfig.buildRobotWrapper()

model = robot.model
nq = model.nq; nv = model.nv; nu = nq; nx = nq+nv
q0 = np.array([0.1, 0.7, 0., 0.7, -0.5, 1.5, 0.])
v0 = np.zeros(nv)
x0 = np.concatenate([q0, v0]).copy()
robot.framesForwardKinematics(q0)
robot.computeJointJacobians(q0)


# # # # # # # # # # # # # # #
###  SETUP CROCODDYL OCP  ###
# # # # # # # # # # # # # # #

# State and actuation model
state = crocoddyl.StateMultibody(model)
actuation = crocoddyl.ActuationModelFull(state)

# Running and terminal cost models
runningCostModel = crocoddyl.CostModelSum(state)
terminalCostModel = crocoddyl.CostModelSum(state)


# Create cost terms 
  # Control regularization cost
uResidual = crocoddyl.ResidualModelControlGrav(state)
uRegCost = crocoddyl.CostModelResidual(state, uResidual)
  # State regularization cost
xResidual = crocoddyl.ResidualModelState(state, x0)
xRegCost = crocoddyl.CostModelResidual(state, xResidual)
  # endeff frame translation cost
endeff_frame_id = model.getFrameId("contact")
# endeff_translation = robot.data.oMf[endeff_frame_id].translation.copy()
endeff_translation = np.array([0.7, 0, 1.1]) # move endeff +30 cm along x in WORLD frame
frameTranslationResidual = crocoddyl.ResidualModelFrameTranslation(state, endeff_frame_id, endeff_translation)
frameTranslationCost = crocoddyl.CostModelResidual(state, frameTranslationResidual)


# Add costs
runningCostModel.addCost("stateReg", xRegCost, 1e-1)
runningCostModel.addCost("ctrlRegGrav", uRegCost, 1e-4)
runningCostModel.addCost("translation", frameTranslationCost, 1)
terminalCostModel.addCost("stateReg", xRegCost, 1e-1)
terminalCostModel.addCost("translation", frameTranslationCost, 1)

# Create Differential Action Model (DAM), i.e. continuous dynamics and cost functions
running_DAM = crocoddyl.DifferentialActionModelFreeFwdDynamics(state, actuation, runningCostModel)
terminal_DAM = crocoddyl.DifferentialActionModelFreeFwdDynamics(state, actuation, terminalCostModel)

# Create Integrated Action Model (IAM), i.e. Euler integration of continuous dynamics and cost
dt = 1e-2
runningModel = crocoddyl.IntegratedActionModelEuler(running_DAM, dt)
terminalModel = crocoddyl.IntegratedActionModelEuler(terminal_DAM, 0.)

# Optionally add armature to take into account actuator's inertia
# runningModel.differential.armature = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.])
# terminalModel.differential.armature = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.])

# Create the shooting problem
T = 2
problem = crocoddyl.ShootingProblem(x0, [runningModel] * T, terminalModel)



# choose scenario: 0 or 1 or 2
option = 0

if option == 0:    
  clip_state_max = np.array([np.inf]*14)
  clip_state_min = -np.array([np.inf]*7 + [0.5]*7)
  clip_ctrl = np.array([np.inf, np.inf , np.inf, np.inf, np.inf, np.inf , np.inf] )
  ConstraintModel = FullConstraintModel(clip_state_min, clip_state_max, -clip_ctrl, clip_ctrl)
  clip_state_end = np.array([np.inf, np.inf, np.inf, np.inf, np.inf, np.inf , np.inf] + [0.001]*7)
  TerminalConstraintModel = FullConstraintModel(-clip_state_end, clip_state_end, -clip_ctrl, clip_ctrl)
  constraintModels = [ConstraintModel] * T + [TerminalConstraintModel]


elif option == 1:
  lmin = np.array([-np.inf, endeff_translation[1], endeff_translation[2]])
  lmax =  np.array([np.inf, endeff_translation[1], endeff_translation[2]])
  # lmin = np.array([-np.inf, -np.inf, -np.inf])
  # lmax =  np.array([np.inf, np.inf, np.inf])
  constraintModels = [EndEffConstraintModel(robot, lmin, lmax)] * (T+1)


elif option == 2:
  constraintModels = [NoConstraint()] * (T+1)



xs = [x0] * (T+1)
us = [np.zeros(nu)] * T 
# ddp = GNMSCPP(problem) 
# ddp = CILQR(problem, constraintModels, "OSQP")
# ddp = CILQR(problem, constraintModels, "ProxQP")
# ddp = CILQR(problem, constraintModels, "sparceADMM")
# ddp = CILQR(problem, constraintModels, "CustomOSQP")
ddp1 = CLQR(problem, constraintModels, "sparceADMM")

ddp2 = CLQR(problem, constraintModels, "Boyd")
ddp1.solve(xs, us, 1)

print(100*"*")

ddp2.solve(xs, us, 1)
print(100*"*")


# print("NORM X_K", np.linalg.norm(np.array(ddp1.xs) - np.array(ddp2.xs)))
# print("NORM U_K", np.linalg.norm(np.array(ddp1.us) - np.array(ddp2.us)))

##### UNIT TEST #####################################

set_tol = 1e-6
dx_relaxed = np.array(ddp1.dx_tilde).flatten()[nx:]
du_relaxed = np.array(ddp1.du_tilde).flatten()
d_relaxed = np.hstack((dx_relaxed, du_relaxed))

print(d_relaxed - ddp2.xtilde_k_1)

assert np.linalg.norm(np.array(ddp1.xs) - np.array(ddp2.xs)) < set_tol, "Test failed"

assert np.linalg.norm(np.array(ddp1.us) - np.array(ddp2.us)) < set_tol, "Test failed"

dx_relaxed = np.array(ddp1.dx_relaxed).flatten()[nx:]
du_relaxed = np.array(ddp1.du_relaxed).flatten()
d_relaxed = np.hstack((dx_relaxed, du_relaxed))
assert np.linalg.norm( d_relaxed- np.array(ddp2.x_k_1)) < set_tol, "Test failed"

xz = np.array(ddp1.xz).flatten()[nx:]
uz = np.array(ddp1.uz).flatten()[:-nu]
z = np.hstack((xz, uz))
assert np.linalg.norm(z - np.array(ddp2.z_k)) < set_tol, "Test failed"

xy = np.array(ddp1.xy).flatten()[nx:]
uy = np.array(ddp1.uy).flatten()[:-nu]
y = np.hstack((xy, uy))
assert np.linalg.norm(y - np.array(ddp2.y_k)) < set_tol, "Test failed"

rho_x = np.array(ddp1.rho_vec_x).flatten()[nx:]
rho_u = np.array(ddp1.rho_vec_u).flatten()[:-nu]
rho = np.hstack((rho_x, rho_u))

assert np.linalg.norm(rho - np.array(ddp2.rho_vec_boyd)) < set_tol, "Test failed"

assert np.linalg.norm(ddp1.rho_estimate_sparse - ddp2.rho_estimate_boyd) < set_tol, "Test failed"

# assert False
# Extract DDP data and plot
# ddp_data = ocp_utils.extract_ocp_data(ddp, ee_frame_name='contact')

# ocp_utils.plot_ocp_results(ddp_data, which_plots="all", labels=None, markers=['.'], colors=['b'], sampling_plot=1, SHOW=True)

# xs_ddp = [x0] * (T+1)
# us_ddp = [np.zeros(nu)] * T 
# ddp.solve(xs_ddp, us_ddp, maxiter=200)

# print(np.linalg.norm(np.array(ddp.us) - np.array(GNMS.us)))
# print(np.linalg.norm(np.array(ddp.xs) - np.array(GNMS.xs)))


