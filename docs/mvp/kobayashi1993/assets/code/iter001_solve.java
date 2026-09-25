/** PaperSim generated contract. */
/**
 * Case: kobayashi1993_dendrite
 * Iteration: iter001
 * Profile SHA-256: 21ea7a5a32d734b02f37c04770c1bff3c53a54698a7a2ba45f0b1f8f9cc63ab4
 * IR SHA-256: cd7058badd0053538a952840a2de6bfb265f1882259f64f37f61b8fe0760f243
 * 
 * Equation-to-feature mapping:
 *   eq3 [control] -> gp
 *   eq4m [constitutive] -> (not a COMSOL feature)
 *   eq4sigma [constitutive] -> (not a COMSOL feature)
 *   eq5 [control] -> gT
 */

import com.comsol.model.*;
import com.comsol.model.util.*;
import java.io.IOException;

/**
 * Solve and export a previously built Kobayashi 1993 MPH.
 *
 * This class is intentionally separate from the deterministic build-only
 * source, as required by the PaperSim comsol-modeling skill.
 */
public final class Kobayashi1993DendriteSolve {
  private static void exportAllSolutions(Model model) throws IOException {
    model.result().numerical("gev1").set("data", "dset2");
    model.result().numerical("gev1").set("innerinput", "all");
    model.result().numerical("gev1").setResult();
    model.result().table("tblGlobal").save("iter001_global.csv");

    model.result().export("data1").set("data", "dset2");
    model.result().export("data1").set("innerinput", "interp");
    model.result().export("data1").set("t", new double[]{0.2, 0.8, 1.4});
    model.result().export("data1").set("filename", "iter001_fields.csv");
    model.result().export("data1").run();
  }

  public static void main(String[] args) throws IOException {
    boolean exportOnly = args.length > 0 && "export-only".equals(args[0]);
    String solved = "iter001_solved.mph";
    String input = exportOnly ? solved : "iter001_built.mph";
    Model model = ModelUtil.load("Kobayashi1993Dendrite", input);
    if (!exportOnly) {
      model.study("std1").run();
    }
    exportAllSolutions(model);
    if (!exportOnly) {
      model.save(solved);
    }
  }
}
