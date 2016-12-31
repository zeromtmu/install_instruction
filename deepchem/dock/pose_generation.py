"""
Generates protein-ligand docked poses using Autodock Vina.
"""
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

__author__ = "Bharath Ramsundar"
__copyright__ = "Copyright 2016, Stanford University"
__license__ = "GPL"

import numpy as np
import os
import pybel
import tempfile
from deepchem.feat import hydrogenate_and_compute_partial_charges
from subprocess import call

class PoseGenerator(object):
  """Abstract superclass for all pose-generation routines."""

  def generate_poses(self, protein_file, ligand_file, out_dir=None):
    """Generates the docked complex and outputs files for docked complex."""
    raise NotImplementedError

def write_conf(receptor_filename, ligand_filename, centroid, box_dims,
               conf_filename, exhaustiveness=None):
  """Writes Vina configuration file to disk."""
  with open(conf_filename, "wb") as f:
    f.write("receptor = %s\n" % receptor_filename)
    f.write("ligand = %s\n\n" % ligand_filename)

    f.write("center_x = %f\n" % centroid[0])
    f.write("center_y = %f\n" % centroid[1])
    f.write("center_z = %f\n\n" % centroid[2])

    f.write("size_x = %f\n" % box_dims[0])
    f.write("size_y = %f\n" % box_dims[1])
    f.write("size_z = %f\n\n" % box_dims[2])

    if exhaustiveness is not None:
      f.write("exhaustiveness = %d\n" % exhaustiveness)

def get_molecule_data(pybel_molecule):
  """Uses pybel to compute centroid and range of molecule (Angstroms)."""
  atom_positions = []
  for atom in pybel_molecule:
    atom_positions.append(atom.coords)
  num_atoms = len(atom_positions)
  protein_xyz = np.asarray(atom_positions)
  protein_centroid = np.mean(protein_xyz, axis=0)
  protein_max = np.max(protein_xyz, axis=0)
  protein_min = np.min(protein_xyz, axis=0)
  protein_range = protein_max - protein_min
  return protein_centroid, protein_range


class VinaPoseGenerator(PoseGenerator):

  def __init__(self, exhaustiveness=1):
    """Initializes Vina Pose generation"""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    self.vina_dir = os.path.join(current_dir, "autodock_vina_1_1_2_linux_x86")
    self.exhaustiveness = exhaustiveness
    if not os.path.exists(self.vina_dir):
      print("Vina not available. Downloading")
      # TODO(rbharath): May want to move this file to S3 so we can ensure it's
      # always available.
      wget_cmd = "wget http://vina.scripps.edu/download/autodock_vina_1_1_2_linux_x86.tgz"
      call(wget_cmd.split())
      print("Downloaded Vina. Extracting")
      download_cmd = "tar xzvf autodock_vina_1_1_2_linux_x86.tgz"
      call(download_cmd.split())
      print("Moving to final location")
      mv_cmd = "mv autodock_vina_1_1_2_linux_x86 %s" % current_dir
      call(mv_cmd.split())
      print("Cleanup: removing downloaded vina tar.gz")
      rm_cmd = "rm autodock_vina_1_1_2_linux_x86.tgz"
      call(rm_cmd.split())
    self.vina_cmd = os.path.join(self.vina_dir, "bin/vina")
      

  def generate_poses(self, protein_file, ligand_file, out_dir=None):
    """Generates the docked complex and outputs files for docked complex."""
    if out_dir is None:
      out_dir = tempfile.mkdtemp()

    # Prepare receptor 
    receptor_name = os.path.basename(protein_file).split(".")[0]
    protein_hyd = os.path.join(out_dir, "%s.pdb" % receptor_name)
    protein_pdbqt = os.path.join(out_dir, "%s.pdbqt" % receptor_name)
    hydrogenate_and_compute_partial_charges(protein_file, "pdb",
                                            hyd_output=protein_hyd,
                                            pdbqt_output=protein_pdbqt,
                                            protein=True)
    # Get protein centroid and range
    receptor_pybel = next(pybel.readfile(str("pdb"), str(protein_hyd)))
    # TODO(rbharath): Need to add some way to identify binding pocket, or this is
    # going to be extremely slow!
    protein_centroid, protein_range = get_molecule_data(receptor_pybel)
    box_dims = protein_range + 5.0

    # Prepare receptor
    ligand_name = os.path.basename(ligand_file).split(".")[0]
    ligand_hyd = os.path.join(out_dir, "%s.pdb" % ligand_name)
    ligand_pdbqt = os.path.join(out_dir, "%s.pdbqt" % ligand_name)

    # TODO(rbharath): Generalize this so can support mol2 files as well.
    hydrogenate_and_compute_partial_charges(ligand_file, "sdf",
                                            hyd_output=ligand_hyd,
                                            pdbqt_output=ligand_pdbqt,
                                            protein=False)

    # Write Vina conf file
    conf_file = os.path.join(out_dir, "conf.txt")
    write_conf(protein_pdbqt, ligand_pdbqt, protein_centroid,
               box_dims, conf_file, exhaustiveness=self.exhaustiveness)

    # Define locations of log and output files
    log_file = os.path.join(out_dir, "%s_log.txt" % ligand_name)
    out_pdbqt = os.path.join(out_dir, "%s_docked.pdbqt" % ligand_name)
    # TODO(rbharath): Let user specify the number of poses required.
    print("About to call Vina")
    call("%s --config %s --log %s --out %s"
         % (self.vina_cmd, conf_file, log_file, out_pdbqt), shell=True)
    # TODO(rbharath): Convert the output pdbqt to a pdb file.

    # Return docked files 
    return protein_hyd, out_pdbqt
