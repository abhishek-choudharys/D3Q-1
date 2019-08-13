"""
Created on May 22, 2016

This should be a simple minimalist run file. It's only responsibility should be to parse the arguments (which agent, user simulator to use) and launch a dialog simulation.

Rule-agent: python run.py --agt 6 --usr 1 --max_turn 40 --episodes 150 --movie_kb_path .\deep_dialog\data\movie_kb.1k.p --run_mode 2

movie_kb:
movie_kb.1k.p: 94% success rate
movie_kb.v2.p: 36% success rate

user goal files:
first turn: user_goals_first_turn_template.v2.p
all turns: user_goals_all_turns_template.p
user_goals_first_turn_template.part.movie.v1.p: a subset of user goal. [Please use this one, the upper bound success rate on movie_kb.1k.json is 0.9765.]

Commands:
Rule: python run.py --agt 5 --usr 1 --max_turn 40 --episodes 150 --movie_kb_path .\deep_dialog\data\movie_kb.1k.p --goal_file_path .\deep_dialog\data\user_goals_first_turn_template.part.movie.v1.p --intent_err_prob 0.00 --slot_err_prob 0.00 --episodes 500 --act_level 1 --run_mode 1

Training:
RL: python run.py --agt 9 --usr 1 --max_turn 40 --movie_kb_path .\deep_dialog\data\movie_kb.1k.p --dqn_hidden_size 80 --experience_replay_pool_size 1000 --episodes 500 --simulation_epoch_size 100 --write_model_dir .\deep_dialog\checkpoints\rl_agent\ --run_mode 3 --act_level 0 --slot_err_prob 0.05 --intent_err_prob 0.00 --batch_size 16 --goal_file_path .\deep_dialog\data\user_goals_first_turn_template.part.movie.v1.p --warm_start 1 --warm_start_epochs 120

Predict:
RL: python run.py --agt 9 --usr 1 --max_turn 40 --movie_kb_path .\deep_dialog\data\movie_kb.1k.p --dqn_hidden_size 80 --experience_replay_pool_size 1000 --episodes 300 --simulation_epoch_size 100 --write_model_dir .\deep_dialog\checkpoints\rl_agent\ --slot_err_prob 0.00 --intent_err_prob 0.00 --batch_size 16 --goal_file_path .\deep_dialog\data\user_goals_first_turn_template.part.movie.v1.p --episodes 200 --trained_model_path .\deep_dialog\checkpoints\rl_agent\agt_9_22_30_0.37000.p --run_mode 3

@author: xiul, t-zalipt, t-shsu
"""


import argparse, json, copy, os
import cPickle as pickle

from deep_dialog.dialog_system import DialogManager, text_to_dict
from deep_dialog.agents import AgentCmd, InformAgent, RequestAllAgent, RandomAgent, EchoAgent, RequestBasicsAgent, AgentDQN
from deep_dialog.usersims import RuleSimulator, ModelBasedSimulator
from deep_dialog.controller import  Discriminator

from deep_dialog import dialog_config
from deep_dialog.dialog_config import *

from deep_dialog.nlu import nlu
from deep_dialog.nlg import nlg

import numpy
import random


"""
Launch a dialog simulation per the command line arguments
This function instantiates a user_simulator, an agent, and a dialog system.
Next, it triggers the simulator to run for the specified number of episodes.
"""

params = {
        'dict_path' : './deep_dialog/data/dicts.v3.p',
        'movie_kb_path': './deep_dialog/data/movie_kb.1k.p',
        'act_set' : './deep_dialog/data/dia_acts.txt',
        'slot_set' : './deep_dialog/data/slot_set.txt',
        'goal_file_path' : './deep_dialog/data/user_goals_first_turn_template.part.movie.v1.p',
        'diaact_nl_pairs' : './deep_dialog/data/dia_act_nl_pairs.v6.json',
        'max_turn' : 40,
        'episodes' : 500,
        'slot_err_prob' : 0.00,
        'slot_err_mode' : 0,
        'intent_err_prob' : 0.00,
        'agt' : 9,
        'usr' : 1,
        'epsilon' : 0.00,
        'nlg_model_path' : './deep_dialog/models/nlg/lstm_tanh_relu_[1468202263.38]_2_0.610.p',
        'nlu_model_path' : './deep_dialog/models/nlu/lstm_[1468447442.91]_39_80_0.921.p',
        'act_level' : 0,
        'run_mode' : 1,
        'auto_suggest' : 0,
        'cmd_input_mode' : 0,
        'experience_replay_pool_size' : 10000,
        'dqn_hidden_size' : 80,
        'batch_size' : 16,
        'gamma' : 0.9,
        'predict_mode' : False,
        'simulation_epoch_size' : 1,
        'warm_start' : 1,
        'warm_start_epochs' : 50,
        'planning_steps' : 4,
        'trained_model_path' : None,
        'o' : './deep_dialog/checkpoints/',
        'write_model_dir' : './deep_dialog/checkpoints/',
        'save_check_point' : 10,
        'success_rate_threshold' : 0.6,
        'split_fold' : 5,
        'learning_phase' : 'all',
        'grounded' : False,
        'boosted' : 1,
        'train_world_model' : 0,
        'save_model' : 1,
        'user_success_rate_threshold' : 1,
        'agent_success_rate_threshold' : 1,
        'pretrain_discriminator' : 0,
        'discriminator_nn_type': 'RNN',
        'world_model_nn_type' : 'MLP',
        'train_discriminator' : 1,
        'model_type' : 'D3Q',
        'filter_experience_by_discriminator' : 1,
        'buffer_size_unit' : 2000,
        'num_exp_store_per_episode_unit' : 10,
        'domain_extension_exp' : 0,
        'planning_step_to_buffer' : 1
        }


seed = 2
numpy.random.seed(seed)
random.seed(seed)

max_turn = params['max_turn']
num_episodes = params['episodes']

agt = params['agt']
usr = params['usr']

dict_path = params['dict_path']
goal_file_path = params['goal_file_path']

# load the user goals from .p file
all_goal_set = pickle.load(open(goal_file_path, 'rb'))

# split goal set
split_fold = params.get('split_fold', 5)
goal_set = {'train':[], 'valid':[], 'test':[], 'all':[]}
for u_goal_id, u_goal in enumerate(all_goal_set):
    if u_goal_id % split_fold == 1:
        goal_set['test'].append(u_goal)
    else:
        goal_set['train'].append(u_goal)
    goal_set['all'].append(u_goal)
# end split goal set


movie_kb_path = params['movie_kb_path']
movie_kb = pickle.load(open(movie_kb_path, 'rb'))

act_set = text_to_dict(params['act_set'])
slot_set = text_to_dict(params['slot_set'])

if not os.path.isdir(params['write_model_dir']):
    os.makedirs(params['write_model_dir'])

'''
# save model config
with open(os.path.join(params['write_model_dir'], "model_config"), "w+") as f:
    for arg in params:
        f.write("{}: {}\n".format(arg, str(getattr(args, arg))))
    f.close()
'''
################################################################################
# a movie dictionary for user simulator - slot:possible values
################################################################################
movie_dictionary = pickle.load(open(dict_path, 'rb'))

dialog_config.run_mode = params['run_mode']
dialog_config.auto_suggest = params['auto_suggest']

################################################################################
#   Parameters for Controller
################################################################################
usersim_params = {}
usersim_params['max_turn'] = max_turn
usersim_params['slot_err_probability'] = params['slot_err_prob']
usersim_params['slot_err_mode'] = params['slot_err_mode']
usersim_params['intent_err_probability'] = params['intent_err_prob']
usersim_params['simulator_run_mode'] = params['run_mode']
usersim_params['simulator_act_level'] = params['act_level']
usersim_params['learning_phase'] = params['learning_phase']
usersim_params['hidden_size'] = params['dqn_hidden_size']


discriminator = Discriminator(movie_dict=movie_dictionary, act_set=act_set, slot_set=slot_set, start_set=goal_set, nn_type=params['discriminator_nn_type'], params=usersim_params)
################################################################################
#   Parameters for Agents
################################################################################
agent_params = {}
agent_params['max_turn'] = max_turn
agent_params['epsilon'] = params['epsilon']
agent_params['agent_run_mode'] = params['run_mode']
agent_params['agent_act_level'] = params['act_level']

agent_params['experience_replay_pool_size'] = params['experience_replay_pool_size']
agent_params['dqn_hidden_size'] = params['dqn_hidden_size']
agent_params['batch_size'] = params['batch_size']
agent_params['gamma'] = params['gamma']
agent_params['predict_mode'] = params['predict_mode']
agent_params['trained_model_path'] = params['trained_model_path']
agent_params['warm_start'] = params['warm_start']
agent_params['cmd_input_mode'] = params['cmd_input_mode']
agent_params['planning_steps'] = params['planning_steps']
agent_params['model_type'] = params['model_type']
agent_params['buffer_size_unit'] = params['buffer_size_unit']
agent_params['planning_step_to_buffer'] = params['planning_step_to_buffer']

if agt == 0:
    agent = AgentCmd(movie_kb, act_set, slot_set, agent_params)
elif agt == 1:
    agent = InformAgent(movie_kb, act_set, slot_set, agent_params)
elif agt == 2:
    agent = RequestAllAgent(movie_kb, act_set, slot_set, agent_params)
elif agt == 3:
    agent = RandomAgent(movie_kb, act_set, slot_set, agent_params)
elif agt == 4:
    agent = EchoAgent(movie_kb, act_set, slot_set, agent_params)
elif agt == 5:
    agent = RequestBasicsAgent(movie_kb, act_set, slot_set, agent_params)
elif agt == 9:
    agent = AgentDQN(movie_kb, act_set, slot_set, agent_params)

################################################################################
#    Add your agent here
################################################################################
else:
    pass

################################################################################
#   Parameters for User Simulators
################################################################################
usersim_params = {}
usersim_params['max_turn'] = max_turn
usersim_params['slot_err_probability'] = params['slot_err_prob']
usersim_params['slot_err_mode'] = params['slot_err_mode']
usersim_params['intent_err_probability'] = params['intent_err_prob']
usersim_params['simulator_run_mode'] = params['run_mode']
usersim_params['simulator_act_level'] = params['act_level']
usersim_params['learning_phase'] = params['learning_phase']
usersim_params['hidden_size'] = params['dqn_hidden_size']
usersim_params['world_model_nn_type'] = params['world_model_nn_type']
usersim_params['buffer_size_unit'] = params['buffer_size_unit']

# print usr
if usr == 0:# real user
    user_sim = RealUser(movie_dictionary, act_set, slot_set, goal_set, usersim_params)
elif usr == 1:
    user_sim = RuleSimulator(movie_dictionary, act_set, slot_set, goal_set, usersim_params)
    user_sim_planning = ModelBasedSimulator(movie_dictionary, act_set, slot_set, goal_set, usersim_params, discriminator)
    agent.set_user_planning(user_sim_planning)
# elif usr == 2:
#     user_sim = ModelBasedSimulator(movie_dictionary, act_set, slot_set, goal_set, usersim_params)

################################################################################
#    Add your user simulator here
################################################################################
else:
    pass

################################################################################
# load trained NLG model
################################################################################
nlg_model_path = params['nlg_model_path']
diaact_nl_pairs = params['diaact_nl_pairs']
nlg_model = nlg()
nlg_model.load_nlg_model(nlg_model_path)
nlg_model.load_predefine_act_nl_pairs(diaact_nl_pairs)

agent.set_nlg_model(nlg_model)
user_sim.set_nlg_model(nlg_model)
user_sim_planning.set_nlg_model(nlg_model)

################################################################################
# load trained NLU model
################################################################################
nlu_model_path = params['nlu_model_path']
nlu_model = nlu()
nlu_model.load_nlu_model(nlu_model_path)

agent.set_nlu_model(nlu_model)
user_sim.set_nlu_model(nlu_model)

################################################################################
# Dialog Manager
################################################################################
dialog_manager = DialogManager(agent, user_sim, user_sim_planning, act_set, slot_set, movie_kb, discriminator)

################################################################################
#   Run num_episodes Conversation Simulations
################################################################################
status = {'successes': 0, 'count': 0, 'cumulative_reward': 0}

simulation_epoch_size = params['simulation_epoch_size']
batch_size = params['batch_size'] # default = 16
warm_start = params['warm_start']
warm_start_epochs = params['warm_start_epochs']
planning_steps = params['planning_steps']

success_rate_threshold = params['success_rate_threshold']
save_check_point = params['save_check_point']


""" Best Model and Performance Records """
best_model = {}
best_res = {'success_rate': 0, 'ave_reward':float('-inf'), 'ave_turns': float('inf'), 'epoch':0}

# best_model['model'] = copy.deepcopy(agent)
best_res['success_rate'] = 0

performance_records = {}
performance_records['success_rate'] = {}
performance_records['ave_turns'] = {}
performance_records['ave_reward'] = {}
performance_records['use_world_model'] = {}
performance_records['agent_world_model_buffer_size'] = {}
performance_records['agent_user_buffer_size'] = {}
performance_records['discriminator_loss'] = {}
performance_records['world_model_loss'] = {}
performance_records['world_model_buffer_size'] = {}


""" Save model """
def save_model(path, agt, success_rate, agent, best_epoch, cur_epoch):
    filename = 'agt_%s_%s_%s_%.5f.p' % (agt, best_epoch, cur_epoch, success_rate)
    filepath = os.path.join(path, filename)
    checkpoint = {}
    if agt == 9: checkpoint['model'] = copy.deepcopy(agent.dqn.model)
    checkpoint['params'] = params
    try:
        pickle.dump(checkpoint, open(filepath, "wb"))
        print 'saved model in %s' % (filepath, )
    except Exception, e:
        print 'Error: Writing model fails: %s' % (filepath, )
        print e


""" save performance numbers """
def save_performance_records(path, agt, records):
    filename = 'agt_%s_performance_records.json' % (agt)
    filepath = os.path.join(path, filename)
    try:
        json.dump(records, open(filepath, "wb"))
        print 'saved model in %s' % (filepath, )
    except Exception, e:
        print 'Error: Writing model fails: %s' % (filepath, )
        print e


def simulation_epoch(simulation_epoch_size):
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    print "+---------------------+"
    print "|      Validation     |"
    print "+---------------------+"
    res = {}
    for episode in xrange(simulation_epoch_size):
        dialog_manager.initialize_episode(warm_start=True)
        episode_over = False
        while(not episode_over):
            episode_over, reward = dialog_manager.next_turn(record_training_data=False, record_training_data_for_user=False)
            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode %s: Success" % (episode))
                else:
                    print("simulation episode %s: Fail" % (episode))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    res['success_rate'] = float(successes)/simulation_epoch_size
    res['ave_reward'] = float(cumulative_reward)/simulation_epoch_size
    res['ave_turns'] = float(cumulative_turns)/simulation_epoch_size
    print ("simulation success rate %s, ave reward %s, ave turns %s" % (res['success_rate'], res['ave_reward'], res['ave_turns']))
    return res


def simulation_dqn():
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    simulation_count = 0
    total_simulation_count = 0
    num_real_exp_this_episode = 0
    max_num_real_exp = params['num_exp_store_per_episode_unit'] * (params['planning_steps'] + 1)
    print "+------------------------------+"
    print "| Collecting Experiences (DQN) |"
    print "+------------------------------+"
    res = {}
    while num_real_exp_this_episode < max_num_real_exp:
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(True)
        episode_over = False
        record_training_data = True
        simulation_count += 1
        while (not episode_over):
            if num_real_exp_this_episode >= max_num_real_exp:
                record_training_data = False
            else:
                num_real_exp_this_episode += 1

            episode_over, reward = dialog_manager.next_turn(record_training_data=record_training_data)
            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print ("simulation episode {}: Success".format(simulation_count))
                else:
                    print ("simulation episode {}: Fail".format(simulation_count))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    total_simulation_count += simulation_count
    res['success_rate'] = float(successes)/total_simulation_count
    res['ave_reward'] = float(cumulative_reward)/total_simulation_count
    res['ave_turns'] = float(cumulative_turns)/total_simulation_count
    print ("simulation success rate %s, ave reward %s, ave turns %s" % (
    res['success_rate'], res['ave_reward'], res['ave_turns']))
    return res


def simulation_ddq():
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    num_real_exp_this_episode = 0
    num_fake_exp_this_episode = 0
    max_num_real_exp = params['num_exp_store_per_episode_unit']
    max_num_fake_exp = params['num_exp_store_per_episode_unit'] * params['planning_steps']

    print "+-----------------------------+"
    print "| Collecting Experiences (DDQ)|"
    print "+-----------------------------+"
    print "+---------------------------+"
    print "| Collecting Experiences    |"
    print "| From Real Human           |"
    print "+---------------------------+"
    res = {}
    total_simulation_count = 0
    simulation_count = 0
    while num_real_exp_this_episode < max_num_real_exp:
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(True)
        episode_over = False
        record_training_data = True
        simulation_count += 1
        while (not episode_over):
            if num_real_exp_this_episode >= max_num_real_exp:
                record_training_data = False
            else:
                num_real_exp_this_episode += 1

            episode_over, reward = dialog_manager.next_turn(
                record_training_data=record_training_data,
                filter_experience_by_discriminator=False)
            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode {}: Success".format(simulation_count))
                else:
                    print("simulation episode {}: Fail".format(simulation_count))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    print "+---------------------------+"
    print "| Collecting Experiences    |"
    print "| From World Model          |"
    print "+---------------------------+"
    total_simulation_count += simulation_count
    simulation_count = 0
    while num_fake_exp_this_episode < max_num_fake_exp:
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(False)
        episode_over = False
        record_training_data = True
        simulation_count += 1
        while (not episode_over):
            if num_fake_exp_this_episode >= max_num_fake_exp:
                record_training_data = False
            else:
                num_fake_exp_this_episode += 1

            episode_over, reward = dialog_manager.next_turn(
                record_training_data=record_training_data,
                filter_experience_by_discriminator=False)

            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode {}: Success".format(simulation_count))
                else:
                    print("simulation episode {}: Fail".format(simulation_count))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    total_simulation_count += simulation_count
    res['success_rate'] = float(successes)/total_simulation_count
    res['ave_reward'] = float(cumulative_reward)/total_simulation_count
    res['ave_turns'] = float(cumulative_turns)/total_simulation_count
    print ("simulation success rate %s, ave reward %s, ave turns %s" % (
    res['success_rate'], res['ave_reward'], res['ave_turns']))
    return res


def simulation_d3q():
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    num_real_exp_this_episode = 0
    num_fake_exp_this_episode = 0
    max_num_real_exp = params['num_exp_store_per_episode_unit']
    max_num_fake_exp = params['num_exp_store_per_episode_unit'] * params['planning_steps']

    print "+------------------------------+"
    print "| Collecting Experiences (D3Q)|"
    print "+------------------------------+"
    print "+---------------------------+"
    print "| Collecting Experiences    |"
    print "| From Real Human           |"
    print "+---------------------------+"
    res = {}
    simulation_count = 0
    total_simulation_count = 0
    while num_real_exp_this_episode < max_num_real_exp:
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(True)
        episode_over = False
        record_training_data = True
        simulation_count += 1
        while (not episode_over):
            if num_real_exp_this_episode >= max_num_real_exp:
                record_training_data = False
            else:
                num_real_exp_this_episode += 1

            episode_over, reward = dialog_manager.next_turn(
                record_training_data=record_training_data,
                filter_experience_by_discriminator=False)
            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode {}: Success".format(simulation_count))
                else:
                    print("simulation episode {}: Fail".format(simulation_count))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    print "+---------------------------+"
    print "| Collecting Experiences    |"
    print "| From World Model          |"
    print "+---------------------------+"
    total_simulation_count += simulation_count
    simulation_count = 0
    while num_fake_exp_this_episode < max_num_fake_exp:
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(False)
        episode_over = False
        record_training_data = True
        simulation_count += 1
        while (not episode_over):
            if num_fake_exp_this_episode >= max_num_fake_exp:
                record_training_data = False

            episode_over, reward, discriminate_check = dialog_manager.next_turn(
                record_training_data=record_training_data,
                filter_experience_by_discriminator=True)

            if discriminate_check and record_training_data:
                num_fake_exp_this_episode += 1

            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode {}: Success".format(simulation_count))
                else:
                    print("simulation episode {}: Fail".format(simulation_count))
                cumulative_turns += dialog_manager.state_tracker.turn_count

    total_simulation_count += simulation_count
    res['success_rate'] = float(successes)/total_simulation_count
    res['ave_reward'] = float(cumulative_reward)/total_simulation_count
    res['ave_turns'] = float(cumulative_turns)/total_simulation_count
    print ("simulation success rate %s, ave reward %s, ave turns %s" % (
    res['success_rate'], res['ave_reward'], res['ave_turns']))
    return res


def simulation_epoch_with_gan_control_filter(simulation_epoch_size, use_world_model=True, filter_experience_by_discriminator=False):
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    print "+------------------------+"
    print "| Collecting Experiences |"
    print "+------------------------+"
    res = {}
    for episode in xrange(simulation_epoch_size):
        # NOTE: dialog_manager.initialize_episode(False) will use world model
        dialog_manager.initialize_episode(not use_world_model)
        episode_over = False
        while (not episode_over):
            episode_over, reward = dialog_manager.next_turn(filter_experience_by_discriminator=filter_experience_by_discriminator)
            cumulative_reward += reward
            if episode_over:
                if reward > 0:
                    successes += 1
                    print("simulation episode %s: Success" % (episode))
                else:
                    print("simulation episode %s: Fail" % (episode))
                cumulative_turns += dialog_manager.state_tracker.turn_count


    res['success_rate'] = float(successes)/simulation_epoch_size
    res['ave_reward'] = float(cumulative_reward)/simulation_epoch_size
    res['ave_turns'] = float(cumulative_turns)/simulation_epoch_size
    print ("simulation success rate %s, ave reward %s, ave turns %s" % (
    res['success_rate'], res['ave_reward'], res['ave_turns']))
    return res


def simulation_epoch_for_pretrain_discriminator(simulation_epoch_size):
    for episode in xrange(simulation_epoch_size):
        dialog_manager.initialize_episode(False)
        episode_over = False
        while (not episode_over):
            episode_over, reward = dialog_manager.next_turn(record_training_data=False, record_training_data_for_user=False)
    return 0


def simulation_epoch_for_discriminator(simulation_epoch_size=1):
    print "run simulation for discriminator..."
    for episode in xrange(simulation_epoch_size):
        experience_list = list()
        dialog_manager.initialize_episode(False)
        episode_over = False
        while (not episode_over):
            experience = dialog_manager.next_turn(simulation_for_discriminator=True)
            experience_list.append(experience)
            if experience[4]:
                if experience[3] > 0:
                    print "success"
                else:
                    print "fail"
            episode_over = experience[4]

    return experience_list


""" Warm_Start Simulation (by Rule Policy) """
def warm_start_simulation():
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    res = {}
    warm_start_run_epochs = 0
    for _ in xrange(1):
        for episode in xrange(warm_start_epochs):
            dialog_manager.initialize_episode(warm_start=True)
            episode_over = False
            while(not episode_over):
                episode_over, reward = dialog_manager.next_turn()
                cumulative_reward += reward
                if episode_over:
                    if reward > 0:
                        successes += 1
                        print ("warm_start simulation episode %s: Success" % (episode))
                    else: print ("warm_start simulation episode %s: Fail" % (episode))
                    cumulative_turns += dialog_manager.state_tracker.turn_count

            warm_start_run_epochs += 1

        if params['boosted']:
            user_sim_planning.train(batch_size, 5)
    import cPickle
    cPickle.dump(agent.experience_replay_pool, open('warm_up_experience_pool_seed%d_r%d.pkl' %(seed, successes),'wb'))
    cPickle.dump(agent.experience_replay_pool_from_model, open('warm_up_experience_pool_seed%d_r%d_sb.pkl' % (seed, successes), 'wb'))
    cPickle.dump(user_sim_planning.training_examples, open('warm_up_experience_pool_seed%d_r%d_user.pkl' %(seed, successes),'wb'))

    agent.warm_start = 2
    res['success_rate'] = float(successes)/warm_start_run_epochs
    res['ave_reward'] = float(cumulative_reward)/warm_start_run_epochs
    res['ave_turns'] = float(cumulative_turns)/warm_start_run_epochs
    print ("Warm_Start %s epochs, success rate %s, ave reward %s, ave turns %s" % (episode+1, res['success_rate'], res['ave_reward'], res['ave_turns']))
    print ("Current experience replay buffer size %s" % (len(agent.experience_replay_pool)))


def warm_start_simulation_preload():
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0

    res = {}
    warm_start_run_epochs = 0

    import cPickle
    agent.experience_replay_pool = cPickle.load(open('warm_up_experience_pool_seed4883_r40.pklGod','rb'))
    user_sim_planning.training_examples = cPickle.load(open('warm_up_experience_pool_seed4883_r40_user.pkl','rb'))
    user_sim_planning.train(batch_size, 5)
    agent.warm_start = 2
    print ("Current experience replay buffer size %s" % (len(agent.experience_replay_pool)))


def run_episodes(count, status):
    successes = 0
    cumulative_reward = 0
    cumulative_turns = 0
    warm_start_for_model = False

    flash_flag = False

    if agt == 9 and params['trained_model_path'] == None and warm_start == 1:
        print ('warm_start starting ...')
        # warm_start_simulation_preload()
        warm_start_simulation()
        print len(agent.experience_replay_pool)
        # raw_input()
        import cPickle
        cPickle.dump(dialog_manager.user_actions_for_dump, open('user_actions.dump','wb'))
        print('warm_start finished, start RL training ...')

    if agt == 9 and params['pretrain_discriminator']:
        print "pretraining the discriminator..."
        # TODO: use argument
        for _ in range(20):
            simulation_epoch_for_pretrain_discriminator(3)
            discriminator_loss = dialog_manager.discriminator.train()
            print "discriminator loss: {}".format(discriminator_loss)

    for episode in xrange(count):
        # warm_start_for_model = params['grounded']
        # simulation_epoch_size = planning_steps + 1
        if params['model_type'] == 'D3Q' and episode == 0:
            simulation_epoch_with_gan_control_filter(3, True)
            simulation_epoch_with_gan_control_filter(3, False)

        # update fixed target network
        agent.dqn.update_fixed_target_network()

        print("Episode: %s" % (episode))
        agent.predict_mode = False
        dialog_manager.initialize_episode(True)
        episode_over = False

        while(not episode_over):
            episode_over, reward = dialog_manager.next_turn(record_training_data_for_user=False)
            cumulative_reward += reward

            if episode_over:
                if reward > 0:
                    print("Successful Dialog!")
                    successes += 1
                else:
                    print("Failed Dialog!")
                cumulative_turns += dialog_manager.state_tracker.turn_count

        # simulation
        if agt == 9 and params['trained_model_path'] == None:
            agent.predict_mode = True
            user_sim_planning.predict_mode = True
            # D3Q
            if params['model_type'] == "D3Q":
                simulation_d3q()
            elif params['model_type'] == "DDQ":
                simulation_ddq()
            elif params['model_type'] == "DQN":
                simulation_dqn()

            # if episode > 50:
            if episode >= 0:
                agent.predict_mode = False
                user_sim_planning.predict_mode = False
                simulation_res = simulation_epoch(50)
            else:
                simulation_res = {}
                simulation_res['success_rate'] = 0
                simulation_res['ave_turns'] = 42
                simulation_res['ave_reward'] = -60
            performance_records['success_rate'][episode] = simulation_res['success_rate']
            performance_records['ave_turns'][episode] = simulation_res['ave_turns']
            performance_records['ave_reward'][episode] = simulation_res['ave_reward']

            # record the buffer size
            performance_records['agent_user_buffer_size'][episode] = len(agent.experience_replay_pool)
            performance_records['agent_world_model_buffer_size'][episode] = len(agent.experience_replay_pool_from_model)

            if simulation_res['success_rate'] > best_res['success_rate']:
                # best_model['model'] = copy.deepcopy(agent)
                best_res['success_rate'] = simulation_res['success_rate']
                best_res['ave_reward'] = simulation_res['ave_reward']
                best_res['ave_turns'] = simulation_res['ave_turns']
                best_res['epoch'] = episode

            user_sim_planning.adversarial = False
            agent.train(batch_size, 1)

            if params['train_world_model']:
                print "+---------------------+"
                print "|  Train World Model  |"
                print "+---------------------+"
                performance_records['world_model_loss'][episode] = user_sim_planning.train(batch_size, 1)
                performance_records['world_model_buffer_size'][episode] = len(user_sim_planning.training_examples)

            if episode > 1 and params['model_type'] == 'D3Q' and params['train_discriminator']:
                print "+---------------------+"
                print "| Train Discriminator |"
                print "+---------------------+"
                discriminator_loss = dialog_manager.discriminator.train()
                performance_records['discriminator_loss'][episode] = discriminator_loss
                print "discriminator loss: {}".format(discriminator_loss)

            agent.predict_mode = False
            print("Simulation success rate %s, Ave reward %s, Ave turns %s, Best success rate %s" % (performance_records['success_rate'][episode], performance_records['ave_reward'][episode], performance_records['ave_turns'][episode], best_res['success_rate']))
            path = '{}/dqn.model.epoch{}.ckpt'.format(params['write_model_dir'], episode)
            if params['save_model'] and episode % 50 == 0:
                agent.save_dqn(path)

            save_performance_records(params['write_model_dir'], agt, performance_records)

        print("Progress: %s / %s, Success rate: %s / %s Avg reward: %.2f Avg turns: %.2f" % (episode+1, count, successes, episode+1, float(cumulative_reward)/(episode+1), float(cumulative_turns)/(episode+1)))
    print("Success rate: %s / %s Avg reward: %.2f Avg turns: %.2f" % (successes, count, float(cumulative_reward)/count, float(cumulative_turns)/count))
    status['successes'] += successes
    status['count'] += count

    # save the model
    path = '{}/dqn.model.epoch{}.ckpt'.format(params['write_model_dir'], '_final')
    if params['save_model']:
        agent.save_dqn(path)

    if agt == 9 and params['trained_model_path'] == None:
        save_performance_records(params['write_model_dir'], agt, performance_records)

run_episodes(num_episodes, status)
