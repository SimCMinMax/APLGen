# Genetic Optimization on Outlaw Rogue APLs

# Assumptions: Talents = 10X0022
# Assume that there's a line in the APL that already takes care of ghostly-strike refreshing.

# Algorithm:
# For each talent, (DS, ANT, VIG), do the following
# We seek to learn a mapping from states to actions.
# States are vectors of four features:
# - Will you cap energy in one GCD?
# - Do you have the opportunity buff?
# - The jolly_roger buff?
# - The broadsides buff?

# Because we allow three potential abilities for each line, there are a total of
# 3 ^ ( (max_cp+1) * (2 ^ n_features) ) potential APLs - this is gigantic! 
# We cannot search the entire space exhaustively. We'll generate candidate APLs and then use DEAP to evolve them.

# A chromosome is a mapping of (max_cp+1) * (2 ^ n_features) lines to a suggested spell (SS, PS, RT)
# Mutation is done by changing a single suggested spell.
# Cross-over is done by breeding five chromosomes and selecting (with majority vote) the spell for each spot.
# Fitness evaluation is done by feeding into SIMC and getting DPS value median.

import random
import subprocess
import re
import os
import numpy as np

def generate_apl(chromosome):
    apl_base = """
rogue="Rogue_Outlaw_T19P_{}"
level=110
race=night_elf
timeofday=day
role=attack
position=back
talents=13{}0023
artifact=44:136683:137472:137365:0:1052:1:1054:1:1057:1:1060:3:1061:6:1063:1:1064:3:1065:3:1066:3:1348:1
spec=outlaw

actions.precombat=flask,type=flask_of_the_seventh_demon
actions.precombat+=/augmentation,type=defiled
actions.precombat+=/food,type=seedbattered_fish_plate
actions.precombat+=/snapshot_stats
actions.precombat+=/stealth
actions.precombat+=/potion,name=deadly_grace
actions.precombat+=/marked_for_death,if=raid_event.adds.in>40
actions.precombat+=/roll_the_bones,if=!talent.slice_and_dice.enabled

actions=variable,name=rtb_reroll,value=((!talent.slice_and_dice.enabled)&(rtb_buffs<=1&!(equipped.thraxis_tricksy_treads&buff.true_bearing.up)))
actions+=/variable,name=ss_useable_noreroll,value=(combo_points<5+talent.deeper_stratagem.enabled-(buff.broadsides.up|buff.jolly_roger.up)-(talent.alacrity.enabled&buff.alacrity.stack<=4))
actions+=/variable,name=ss_useable,value=((talent.anticipation.enabled&(combo_points<4))|(!talent.anticipation.enabled&(variable.rtb_reroll&(combo_points<4+talent.deeper_stratagem.enabled)|!variable.rtb_reroll&variable.ss_useable_noreroll)))

actions+=/call_action_list,name=bf
actions+=/call_action_list,name=cds
actions+=/call_action_list,name=stealth
actions+=/death_from_above,if=energy.time_to_max>2&!variable.ss_useable_noreroll
actions+=/slice_and_dice,if=!variable.ss_useable&buff.slice_and_dice.remains<target.time_to_die&buff.slice_and_dice.remains<(1+combo_points)*1.8
actions+=/roll_the_bones,if=!variable.ss_useable&buff.roll_the_bones.remains<target.time_to_die&(buff.roll_the_bones.remains<=3|variable.rtb_reroll)
actions+=/killing_spree,if=energy.time_to_max>5|energy<15
actions+=/call_action_list,name=core_rotation

actions.bf=cancel_buff,name=blade_flurry,if=equipped.shivarran_symmetry&cooldown.blade_flurry.up&buff.blade_flurry.up&spell_targets.blade_flurry>=2|spell_targets.blade_flurry<2&buff.blade_flurry.up
actions.bf+=/blade_flurry,if=spell_targets.blade_flurry>=2&!buff.blade_flurry.up

actions.cds=potion,name=deadly_grace,if=buff.bloodlust.react|target.time_to_die<=25|buff.adrenaline_rush.up
actions.cds+=/use_item,slot=trinket2
actions.cds+=/blood_fury
actions.cds+=/berserking
actions.cds+=/arcane_torrent,if=energy.deficit>40
actions.cds+=/cannonball_barrage,if=spell_targets.cannonball_barrage>=1
actions.cds+=/adrenaline_rush,if=!buff.adrenaline_rush.up
actions.cds+=/marked_for_death,target_if=min:target.time_to_die,if=target.time_to_die<combo_points.deficit|((raid_event.adds.in>40|buff.true_bearing.remains>15)&combo_points.deficit>=4+talent.deeper_strategem.enabled+talent.anticipation.enabled)
actions.cds+=/sprint,if=equipped.thraxis_tricksy_treads&!variable.ss_useable
actions.cds+=/curse_of_the_dreadblades,if=combo_points.deficit>=4&(!talent.ghostly_strike.enabled|debuff.ghostly_strike.up)

actions.stealth=variable,name=stealth_condition,value=(combo_points.deficit>=2+2*(talent.ghostly_strike.enabled&!debuff.ghostly_strike.up)+buff.broadsides.up&energy>60&!buff.jolly_roger.up&!buff.hidden_blade.up&!buff.curse_of_the_dreadblades.up)
actions.stealth+=/ambush
actions.stealth+=/vanish,if=variable.stealth_condition
actions.stealth+=/shadowmeld,if=variable.stealth_condition

actions.core_rotation=ghostly_strike,if=talent.ghostly_strike.enabled&(debuff.ghostly_strike.remains<4.5|cooldown.curse_of_the_dreadblades.remains<3)&combo_points.deficit>=1+buff.broadsides.up&!buff.curse_of_the_dreadblades.up&(combo_points>=3|variable.rtb_reroll&time>=10)
{}

head=vigilant_bondbreaker_headdress,id=134446,bonus_id=1727
neck=chaosforged_necklace,id=137458,bonus_id=1727,enchant=mark_of_the_distant_army
shoulders=charskin_mantle,id=137510,bonus_id=1727
back=stole_of_malefic_repose,id=134404,bonus_id=1727,enchant=binding_of_agility
chest=chestguard_of_insidious_desire,id=137514,bonus_id=1727
wrists=cryptwalker_bracers,id=137425,bonus_id=1727
hands=guileful_intruder_handguards,id=137480,bonus_id=1727
waist=ravens_veil_belt,id=139243,bonus_id=1727
legs=brinewashed_leather_pants,id=134238,bonus_id=1727
feet=tunnel_trudger_footguards,id=137397,bonus_id=1727
finger1=band_of_the_wyrm_matron,id=134524,bonus_id=1727,enchant=binding_of_versatility
finger2=jeweled_signet_of_melandrus,id=134542,bonus_id=1727,enchant=binding_of_versatility
trinket1=chaos_talisman,id=137459,bonus_id=1727
trinket2=tirathons_betrayal,id=137537,bonus_id=1727
main_hand=the_dreadblades,id=128872,bonus_id=742,gem_id=136683/137472/137365,relic_id=1727/1727/1727
off_hand=the_dreadblades,id=134552
    """

    return apl_base.format(chromosome, tier_three_talent(chromosome), generate_core_rotation_string(chromosome))

def random_chromosome(tier_three_talent):
    # Generates a random list of the correct length, filled randomly with (0, 1, 2)
    MAX_CP = 5
    if tier_three_talent == 1: # DS
        MAX_CP = 6
    elif tier_three_talent == 2: # ANT
        MAX_CP = 8
    # Chromosome length is (MAX_CP + 1) * (2 ^ n_features)
    chromosome_length = (MAX_CP + 1) * (2 ** 4)
    return "".join([random.choice(("0","1","2")) for _ in range(chromosome_length) ])

def tier_three_talent(chromosome):
    if len(chromosome) == (5 + 1) * (2 ** 4):
        tier_three_talent = 3
    elif len(chromosome) == (6 + 1) * (2 ** 4):
        tier_three_talent = 1
    elif len(chromosome) == (8 + 1) * (2 ** 4):
        tier_three_talent = 2
    else:
        raise RuntimeException("Bad tier three talent")
    return tier_three_talent


def generate_core_rotation_string(chromosome):
    ABILITIES = ["saber_slash", "pistol_shot", "run_through"] # in the chromosome, this is (0, 1, 2)
    MAX_CP = 5
    if tier_three_talent(chromosome) == 1:
        MAX_CP = 6
    elif tier_three_talent(chromosome) == 2:
        MAX_CP = 8
    core_rotation = ""
    index = 0
    for current_cp in range(MAX_CP+1):
        for energy_capping in (True, False):
            for opportunity_buff in (True, False):
                for jolly_roger_buff in (True, False):
                    for broadsides_buff in (True, False):
                        spell = ABILITIES[int(chromosome[index])]
                        core_rotation += "actions.core_rotation+=/%s,if=combo_points=%s&energy.time_to_max%s1&buff.opportunity.%s&buff.jolly_roger.%s&buff.broadsides.%s" % (spell, current_cp, "<" if energy_capping else ">=", "up" if opportunity_buff else "down", "up" if jolly_roger_buff else "down", "up" if broadsides_buff else "down")
                        core_rotation +="\n"
                        index += 1
    return core_rotation

def evaluate_chromosomes(iterations, chromosomes):
    batched_evaluation_string = """
optimal_raid=1
iterations=%s
""" % iterations

    dps_values = {}
    for chromosome in chromosomes:
        apl = generate_apl(chromosome)

        filename = "Rogue_Outlaw_T19P_{}.simc".format(chromosome)
        with open(filename, "w") as f:
            f.write(apl)
        batched_evaluation_string += filename + "\n"

    batchfile = "Rogue_Outlaw_T19P_Genetic_Evolution.simc"
    with open(batchfile, "w") as f:
        f.write(batched_evaluation_string)

    # Janky as fuck. Prefer to use JSON output when that works, but.. scrape stdout for "DPS Ranking" block, parse.
    completed_process = subprocess.run(["simc", "Rogue_Outlaw_T19P_Genetic_Evolution.simc"], stdout=subprocess.PIPE, universal_newlines=True)
    output = completed_process.stdout
    dps_ranking_ind = output.find("DPS Ranking")
    hps_ranking_ind = output.find("HPS Ranking")
    dps_output_string = output[dps_ranking_ind:hps_ranking_ind].strip()
    print(dps_output_string)
    dps_lines = [line.strip() for line in dps_output_string.split("\n")[2:]]
    for line in dps_lines:
        (dps, _, name) = line.split()
        chromosome = name.split("_")[3]
        dps_values[chromosome] = int(dps)

    # Clean up
    for chromosome in chromosomes:
        filename = "Rogue_Outlaw_T19P_{}.simc".format(chromosome)
        os.remove(filename)
    os.remove(batchfile)

    return dps_values

def merge(chromosomes):
    def majority(index):
        genes = [c[index] for c in chromosomes]
        return max(set(genes), key=genes.count)
    # Takes majority vote of these chromosomes
    chromo_len = len(chromosomes[1])
    return "".join([majority(i) for i in range(chromo_len)])

def crossover(parents):
    # Take the first half of the first parent etc
    father = parents[0]
    mother = parents[1]
    chromo_len = len(father)
    return father[:chromo_len] + mother[chromo_len:]


def mutate(chromosome):
    pos = random.randint(0, len(chromosome[1]))
    current = chromosome[pos]
    avail = ["0", "1", "2"]
    avail.remove(current)
    return chromosome[0:pos] + random.choice(avail) + chromosome[pos:]

def evolve(population, retain_prob=0.20, select_prob=0.10, mutate_prob=0.85, sim_iters=25):
    print("Evolve called on population of size %d" % len(population))
    fitness = evaluate_chromosomes(sim_iters, population)
    ranked_chromosomes = sorted(fitness, key=fitness.get, reverse=True)
    retain_count = int(len(population) * retain_prob)
    # Select `retain` fraction of best parents to keep.
    parents = ranked_chromosomes[:retain_count]
    print("Starting with %s parents" % retain_count)
    for parent in parents:
        print("Parent %s has fitness %d" % (parent, fitness[parent]))

    # Randomly select some `select` fraction of less good individuals for reproduction.
    for chromo in ranked_chromosomes[retain_count:]:
        if random.random() < select_prob:
            print("Adding inferior candidate %s due to random selection!" % chromo)
            parents.append(chromo)

    # Mutate some parents:
    for parent in parents:
        if random.random() < mutate_prob:
            print("Mutating parent %s" % parent)
            parent = mutate(parent)

    # Crossover parents to create children
    parent_length = len(parents)
    print("Have %d parents pre-reproduction" % parent_length)
    desired_length = len(population) - len(parents)
    print("Need to spawn %d children" % desired_length)
    children = []
    while len(children) < desired_length:
        reproducers = np.random.choice(parents, 2, replace=False)
        new_child = crossover(reproducers)
        print("Child produced: %s" % new_child)
        children.append(new_child)

    parents.extend(children)
    return parents

def main():
    TIER_THREE_TALENT = 1
    population_size = 30

    max_iters = 3
    simc_iters = 10

    current_population = set([random_chromosome(TIER_THREE_TALENT) for _ in range(population_size)])

    iteration = 0
    while iteration < max_iters:
        current_population = evolve(current_population)
        iteration += 1

main()
