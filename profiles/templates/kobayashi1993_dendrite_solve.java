/** PaperSim generated contract. */
/*__GENERATED_HEADER__*/

import com.comsol.model.*;
import com.comsol.model.util.*;
import java.io.IOException;

/**
 * Solve and export a previously built Kobayashi 1993 MPH.
 *
 * This class is intentionally separate from the deterministic build-only
 * source, as required by the PaperSim comsol-modeling skill.
 */
public final class __SOLVE_CLASS__ {
  private static void exportAllSolutions(Model model) throws IOException {
    model.result().numerical("gev1").set("data", "dset2");
    model.result().numerical("gev1").set("innerinput", "all");
    model.result().numerical("gev1").setResult();
    model.result().table("tblGlobal").save("__GLOBAL_CSV__");

    model.result().export("data1").set("data", "dset2");
    model.result().export("data1").set("innerinput", "interp");
    model.result().export("data1").set("t", new double[]{0.2, 0.8, 1.4});
    model.result().export("data1").set("filename", "__FIELDS_CSV__");
    model.result().export("data1").run();
  }

  public static void main(String[] args) throws IOException {
    boolean exportOnly = args.length > 0 && "export-only".equals(args[0]);
    String solved = "__SOLVED_MPH__";
    String input = exportOnly ? solved : "__BUILD_MPH__";
    Model model = ModelUtil.load("__MODEL_NAME__", input);
    if (!exportOnly) {
      model.study("std1").run();
    }
    exportAllSolutions(model);
    if (!exportOnly) {
      model.save(solved);
    }
  }
}
