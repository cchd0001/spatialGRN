#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date: Created on 26 Oct 2023 13:37
# @Author: Yao LI
# @File: spagrn/receptor_simulation.py

import os
import pandas as pd
import scanpy as sc
from pyarrow import feather
import pyarrow
from random import sample
from typing import Union

import sys
sys.path.append('/dellfsqd2/ST_OCEAN/USER/liyao1/07.spatialGRN/')
from spagrn_debug.plot import plot_celltype, plot_gene


class Simulator(object):
    """
    Down-stream
    handle scMultiSim outputs
    """

    def __init__(self):
        self.data = None
        self.tfs = None
        self.tf_names = None
        self.motif_names = None
        self.receptors = None
        self.ligands = None
        self.targets = None
        self.total_genes = None

        self.lr_gt = None
        self.grn_gt = None

        self.counts = None
        self.noise_ids = None  # noise genes
        self.real_ids = None  # real genes
        self.total_name = None
        self.total_id = None

        self.name_df = None

        self.coor = None
        self.celltypes = None

    def get_lr(self, df):
        """
        Load Ligand-Receptor ground truth if available
        :param df:
        :return:
        """
        self.lr_gt = df
        self.receptors = list(set(df.receptor))
        self.ligands = list(set(df.ligand))

    def get_tg(self, df):
        """
        Load TF-Target ground truth (must have)
        :param df:
        :return:
        """
        self.grn_gt = df
        self.targets = list(set(df['regulated.gene']))
        self.tfs = list(set(df['regulator.gene']))

    def recognize_ids(self):
        """
        for counts gene index
        :return:
        """
        if self.counts:
            self.total_genes = list(self.counts.index)
            self.noise_ids = [i for i in self.total_genes if 'gene' in i]
            self.real_ids = [i for i in self.total_genes if 'gene' not in i]
        else:
            raise ValueError("Expression matrix is not available, load expression matrix first")

    def add_coor(self, value: Union[str, pd.DataFrame]):
        if isinstance(value, pd.DataFrame):
            self.coor = value
        elif isinstance(value, str):
            self.coor = pd.read_csv(fn, index_col=0)

    def add_celltypes(self, value: Union[str, pd.DataFrame]):
        if isinstance(value, pd.DataFrame):
            self.celltypes = value
        elif isinstance(value, str):
            self.celltypes = pd.read_csv(fn, index_col=0)

    def load_exp(self, df: pd.DataFrame):
        """
        when loading only one csv file created by scMultiSim
        :param df:
        :return:
        """
        self.counts = df
        self.recognize_ids()

    def load_multi_samples(self):
        """
        when loading multiple csv files generated by scMultiSim
        :return:
        """
        # Load in needed data
        df_list = []
        n = 0
        for num, tf in enumerate(self.tfs[:5]):
            df2 = pd.read_csv(f'counts_{tf}.csv', index_col=0)
            new_cell_num = df2.shape[1]
            new_cell_names = [f'cell{x}' for x in list(range(n + 1, n + new_cell_num + 1))]
            df2.columns = new_cell_names
            n = n + new_cell_num
            df_list.append(df2)
        # merge into one dataframe
        df = pd.concat(df_list, axis=1).fillna(0).astype(int)
        df3 = pd.read_csv('counts_addition.csv', index_col=0)
        gene_index = [i if 'gene' not in i else f'{i}3' for i in list(df3.index)]
        df3.index = gene_index
        df = pd.concat([df, df3]).fillna(0).astype(int)
        # self.noise_ids = [i for i in list(df.index) if 'gene' in i]
        self.counts = df
        self.recognize_ids()

    def load_multiple_gts(self):
        """
        multiple GRN gts
        :return:
        """
        pass

    def assign_gene_names(self, rdb: pd.DataFrame, tf_motif_dir):
        """

        :param rdb:
        :param tf_motif_dir:
        :return:
        """
        grn_dir = get_dir(self.grn_gt, self.tfs)
        # 1. for targets:
        # tf targets names, assign real names to tf targets. choose top n genes for each motif(TF).
        for tf in self.tfs:
            current_len = len(self.total_name)  # find current total_name number
            one_motif = tf_motif_dir[tf_id_dir[tf]]  # for each motif, find its gene rankings
            # find top genes for the motif
            sub = rdb[rdb.motifs == one_motif].drop('motifs', axis=1)  # remove motif column, only sort gene columns
            sorted_sub = sub.sort_values(by=(sub.index.values[0]), axis=1)  # sort columns (genes) by rank numbers
            top_num = len(grn_dir[tf])
            self.total_id += grn_dir[tf]
            # match real gene name with gene id
            for tg in sorted_sub.columns:
                if tg not in self.total_name:
                    self.total_name.append(tg)
                if len(self.total_name) == (current_len + top_num):
                    break

        # at this point, total names are unique, total ids have duplicates
        # remove duplicates
        name_df1 = pd.DataFrame({'id': self.total_id,
                                 'name': list(self.total_name)}).drop_duplicates(subset='id', keep='first').astype(str)
        self.total_name = list(name_df1.name)
        self.total_id = list(name_df1.id)
        # at this point, len(set(total_name)) should equal to len(set(total_id))
        assert name_df.duplicated().sum().sum() == 0
        self.name_df = name_df1
        return name_df1

    def assign_name_addition(self, rdb, gene_id_list: list):
        """
        based on rest_rdb_names, when rest_rdb_names =
        :param rdb:
        :param gene_id_list: e.g noise_ids
        :return:
        """
        # PART TWO
        # some of the gene names are used. find out the rest unused gene names,
        # to avoid assign used gene name to noise genes and ligand and receptors
        total_rdb_names = set(rdb.columns) - set('motifs')
        rest_rdb_names = list(total_rdb_names - set(self.total_name))
        # 2. for noise genes
        noise_genes_names = sample(rest_rdb_names, k=len(gene_id_list))
        # !! random.choices returns duplicated items, use random.sample instead
        # add noise names into total_name
        self.total_name += noise_genes_names
        self.total_id += gene_id_list

        # create names df
        name_df = pd.DataFrame({'id': self.total_id,
                                'name': list(self.total_name)}).drop_duplicates(subset='id', keep='first').astype(str)
        assert name_df.duplicated().sum().sum() == 0
        self.name_df = name_df
        return name_df

    # def xx(self, rest_rdb_names, ligand_ids: list):
    #     """
    #     based on rest_rdb_names
    #     ligand_ids = list(set(lr_gt.ligand))
    #     :param rest_rdb_names:
    #     :param ligand_ids:
    #     :return:
    #     """
    #     # 3. for ligands
    #     rest_rdb_names = list(set(rest_rdb_names) - set(self.total_name))
    #     ligand_genes_names = sample(rest_rdb_names, k=len(ligand_ids))
    #     self.total_name += ligand_genes_names
    #     self.total_id += ligand_ids
    #     return self.total_name, self.total_id

    # # 4. for receptor genes that are not TF targets
    # rest_rdb_names = list(set(rest_rdb_names) - set(self.total_name))
    # receptors_not_targets_ids = set(lr_gt.receptor) - set(grn_gt['regulated.gene'])
    # receptors_not_targets_names = sample(rest_rdb_names, k=len(receptors_not_targets_ids))
    # self.total_name += receptors_not_targets_names
    # self.total_id += receptors_not_targets_ids

    def to_anndata(self):
        """

        :param celltypes: cell types
        :param coor: cell coordinates
        :param name_df: simulated ID - gene name
        :return: anndata.Anndata
        """
        df = self.counts.T
        adata = sc.AnnData(df)
        adata.obs['cells'] = list(df.index)
        adata.var['genes'] = list(df.columns)
        if self.celltypes:
            adata.obs['celltype'] = self.celltypes['cell.type']
        if self.coor:
            adata.obsm['spatial'] = self.coor.iloc[:int(df.shape[0])]
        data_genes = adata.var.copy()
        data_genes = data_genes['genes'].replace(list(self.name_df['id']), list(self.name_df['name']))
        data_genes = data_genes.to_frame()
        adata.var = data_genes
        adata.var_names = adata.var['genes']
        return adata


class RankingDatabase:
    def __init__(self, rdb: pd.DataFrame):
        self.rdb = rdb
        self.total_rdb_names = None
        self.rest_rdb_names = None


def get_dir(gt: pd.DataFrame, regulators, regulator_key='regulator.gene', value_key='regulator.effect',
            regulated_key='regulated.gene'):
    """
    Create dictionaries to map TF names to motif names and TFs to TF names
    :param gt:
    :param regulators: regulator: TF or ligand
    :param regulator_key:
    :param value_key:
    :param regulated_key:
    :return:
    """
    dir = {}
    for reg in regulators:
        sub = gt[gt[regulator_key] == reg]
        sorted_sub = sub.sort_values(by=value_key, ascending=False)
        dir[reg] = list(sorted_sub[regulated_key])
    return dir


def convert_gene_ids_to_names(params_dir, tfs, tf_names, motif_names):
    """

    :param params_dir:
    :param tfs:
    :param tf_names:
    :param motif_names:
    :return:
    """
    # Read gene ids from files
    ids_list = []
    for tf in tfs[:5]:
        _ids = pd.read_csv(f'{params_dir}/GRN_params_{tf}.csv')
        ids_list.append(_ids)
    ids_add = pd.read_csv(f'{params_dir}/GRN_params_addition.csv')
    ids = pd.concat(ids_list + [ids_add]).drop_duplicates()

    # Create a dictionary to store regulator-target gene relationships
    tg_dir = {}
    for tf in tfs:
        sub = ids[ids['regulator.gene'] == tf]
        sorted_sub = sub.sort_values(by='regulator.effect', ascending=False)
        tg_dir[tf] = list(sorted_sub['regulated.gene'])

    # Create dictionaries to map TF names to motif names and TFs to TF names
    tf_motif_dir = dict(zip(tf_names, motif_names))
    tf_id_dir = dict(zip(tfs, tf_names))

    # Prepare lists for gene names and noise names
    total_name = tf_names.copy()
    total_id = tfs.copy()
    noise_name = []

    return tg_dir, tf_motif_dir, tf_id_dir, total_name, total_id, noise_name


def assign_gene_names_og(tfs: list, rdb: pd.DataFrame, tf_motif_dir, grn_gt: pd.DataFrame, lr_gt: pd.DataFrame,
                      total_name: list, total_id: list, noise_ids: list):
    """
    tested, worked
    :param tfs:
    :param rdb:
    :param grn_dir:
    :param total_name:
    :param total_id:
    :param noise_ids:
    :return:
    """
    grn_dir = get_dir(grn_gt, tfs)
    # 1. for targets:
    # tf targets names, assign real names to tf targets. choose top n genes for each motif(TF).
    for tf in tfs:
        current_len = len(total_name)  # find current total_name number
        one_motif = tf_motif_dir[tf_id_dir[tf]]  # for each motif, find its gene rankings
        # find top genes for the motif
        sub = rdb[rdb.motifs == one_motif].drop('motifs', axis=1)  # remove motif column, only sort gene columns
        sorted_sub = sub.sort_values(by=(sub.index.values[0]), axis=1)  # sort columns (genes) by rank numbers
        top_num = len(grn_dir[tf])
        total_id += grn_dir[tf]
        # match real gene name with gene id
        for tg in sorted_sub.columns:
            if tg not in total_name:
                total_name.append(tg)
            if len(total_name) == (current_len + top_num):
                break

    # at this point, total names are unique, total ids have duplicates
    # remove duplicates
    name_df1 = pd.DataFrame({'id': total_id, 'name': list(total_name)}).drop_duplicates(subset='id',
                                                                                        keep='first').astype(str)
    # 2023-11-01: remove receptor genes. receptor gene names will be assigned later on
    name_df1 = name_df1[~name_df1['id'].isin(list(set(lr_gt.receptor)))]

    total_name = list(name_df1.name)
    total_id = list(name_df1.id)
    # at this point, len(set(total_name)) should equal to len(set(total_id))

    # PART TWO
    # some of the gene names are used. find out the rest unused gene names,
    # to avoid assign used gene name to noise genes and ligand and receptors
    total_rdb_names = set(rdb.columns) - set('motifs')
    rest_rdb_names = list(total_rdb_names - set(total_name))
    # 2. for noise genes
    from random import sample
    noise_genes_names = sample(rest_rdb_names, k=len(noise_ids))
    # !! random.choices returns duplicated items, use random.sample instead
    # add noise names into total_name
    total_name += noise_genes_names
    total_id += noise_ids

    # 2023-11-01: ligands and receptors names should from LR files
    niche_mouse = pd.read_csv('/dellfsqd2/ST_OCEAN/USER/liyao1/07.spatialGRN/resource/lr_network_mouse.csv')
    ligand_names = set(niche_mouse['from'])
    # 3. for ligands
    rest_names = list(ligand_names - set(total_name))
    ligand_ids = list(set(lr_gt.ligand))
    ligand_genes_names = sample(rest_names, k=len(ligand_ids))
    total_name += ligand_genes_names
    total_id += ligand_ids
    # 4. for receptor genes that are not TF targets
    receptor_names = set(niche_mouse['to'])
    rest_names = list(receptor_names - set(total_name))
    receptor_ids = list(set(lr_gt.receptor))
    receptor_names = sample(rest_names, k=len(receptor_ids))
    total_name += receptor_names
    total_id += receptor_ids
    # receptors_not_targets_ids = set(lr_gt.receptor) - set(grn_gt['regulated.gene'])
    # receptors_not_targets_names = sample(rest_names, k=len(receptors_not_targets_ids))
    # total_name += receptors_not_targets_names
    # total_id += receptors_not_targets_ids

    # 2023-11-02: ligands and receptors names should from LR files AND should be lower ranked genes of motifs

    # create names df
    name_df = pd.DataFrame({'id': total_id,
                            'name': list(total_name)}).drop_duplicates(subset='id', keep='first').astype(str)
    assert name_df.duplicated().sum().sum() == 0
    return name_df


# create anndata
def to_anndata(counts: pd.DataFrame, celltypes: pd.DataFrame, coor: pd.DataFrame, name_df: pd.DataFrame):
    """

    :param counts: expression data. genes (row) x cells (col)
    :param celltypes: cell types
    :param coor: cell coordinates
    :param name_df: simulated ID - gene name
    :return: anndata.Anndata
    """
    df = counts.T
    adata = sc.AnnData(df)
    adata.obs['cells'] = list(df.index)
    adata.var['genes'] = list(df.columns)
    adata.obs['celltype'] = celltypes['cell.type']
    adata.obsm['spatial'] = coor.iloc[:int(df.shape[0])]
    data_genes = adata.var.copy()
    data_genes = data_genes['genes'].replace(list(name_df['id']), list(name_df['name']))
    data_genes = data_genes.to_frame()
    adata.var = data_genes
    adata.var_names = adata.var['genes']
    return adata


if __name__ == '__main__':
    # 1. LOAD SIMULATED DATA
    fn_base = '/dellfsqd2/ST_OCEAN/USER/liyao1/07.spatialGRN/exp/07.simulation/ver9'
    coor = pd.read_csv(os.path.join(fn_base, 'coord_5types.csv'), index_col=0)
    counts = pd.read_csv(os.path.join(fn_base, 'counts_5types_100genes.csv'), index_col=0)
    celltypes = pd.read_csv(os.path.join(fn_base, 'celltype_5types.csv'), index_col=0)
    grn_gt = pd.read_csv(os.path.join(fn_base, 'GRN_parameter.csv'))
    grn_gt = grn_gt[grn_gt['regulator.gene'] != 10]
    lr_gt = pd.read_csv(os.path.join(fn_base, 'LR_parameter_100.csv'))
    noise_ids = [i for i in counts.index if 'gene' in i]
    tfs = list(set(grn_gt['regulator.gene']))  # 5 tfs

    # 2. REAL GENE NAMES
    # 2.1 ranking database
    fn = '/dellfsqd2/ST_OCEAN/USER/liyao1/06.stereopy/database/dm6_v10_clust.genes_vs_motifs.rankings.feather'
    rdb = pyarrow.feather.read_feather(fn)
    # 2.2 TF real names
    tf_names = ['Adf1', 'Aef1', 'grh', 'kn', 'tll']
    motif_names = ['bergman__Adf1', 'bergman__Aef1', 'bergman__grh', 'metacluster_172.20', 'metacluster_140.5']

    # params_dir = '/dellfsqd2/ST_OCEAN/USER/liyao1/07.spatialGRN/exp/07.simulation/ver7'
    # tg_dir, tf_motif_dir, tf_id_dir, total_name, total_id, noise_name = convert_gene_ids_to_names(params_dir, tfs,
    #                                                                                               tf_names, motif_names)

    tf_motif_dir = dict(zip(tf_names, motif_names))
    tf_id_dir = dict(zip(tfs, tf_names))

    # Prepare lists for gene names and noise names
    total_name = tf_names.copy()
    total_id = tfs.copy()
    noise_name = []

    name_df = assign_gene_names_og(tfs, rdb, tf_motif_dir, grn_gt, lr_gt, total_name, total_id, noise_ids)
    name_df.to_csv('name_df.csv', index=False)

    adata = to_anndata(counts, celltypes, coor, name_df)
    adata.write_h5ad('lr.h5ad')

    # plot data
    names_dir = dict(zip(name_df.id, name_df.name))
    tf_ids = list(set(grn_gt['regulator.gene']))
    tfs = list(name_df[name_df.id.isin(tf_ids)].name)

    plot_celltype(adata, color='celltype', prefix='lr_celltypes', custom_labels=tfs)

    receptors = set(lr_gt.receptor)
    for r in receptors:
        rn = names_dir[r]
        plot_gene(adata, 'spatial', rn, f'{rn}.png')


