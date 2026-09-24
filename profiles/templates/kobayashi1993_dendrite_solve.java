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
  private static double[] comparisonTimes(double finalTime) {
    if (finalTime >= 1.4 - 1e-12) {
      return new double[]{0.2, 0.8, 1.4};
    }
    if (finalTime >= 0.8 - 1e-12) {
      return new double[]{0.2, 0.8};
    }
    if (finalTime >= 0.2 - 1e-12) {
      return new double[]{0.2};
    }
    return new double[]{finalTime};
  }

  public static void main(String[] args) throws IOException {
    Model model = ModelUtil.load("__MODEL_NAME__", "__BUILD_MPH__");
    model.study("std1").run();
    model.result().numerical("gev1").setResult();
    model.result().table("tblGlobal").save("__GLOBAL_CSV__");
    model.result().export("data1").set("innerinput", "interp");
    model.result().export("data1").set(
        "t", comparisonTimes(model.param().evaluate("tfinal")));
    model.result().export("data1").set("filename", "__FIELDS_CSV__");
    model.result().export("data1").run();
    model.save("__SOLVED_MPH__");
  }
}
