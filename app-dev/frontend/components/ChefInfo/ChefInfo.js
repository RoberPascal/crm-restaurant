"use client";

import { Description } from "../Description/Description";
import styles from "./ChefInfo.module.scss";

export const ChefInfo = ({ chef }) => {
  return (
    <div className={styles.chef}>
      <h2>{chef.name}</h2>
      <Description text={chef.description} />
      <img src={chef.photo} alt={chef.name} className={styles.photo} />
    </div>
  );
};
